"use client";

import Link from "next/link";
import { memo, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import Markdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { FoldLevel, TextFoldDocument, TextFoldUnit } from "@/lib/schema";
import { serializeTextFold } from "@/lib/textfold";
import { LEVEL_LABELS, LEVEL_ORDER, foldContext, linksFrom, nextStep, provenanceLine, unitView, withReferences } from "@/lib/fold-view";
import type { FoldContext } from "@/lib/fold-view";

// OpenPaper's folded reader. It renders a textfold/doc document in the page
// with the app's own Markdown renderer and tokens: no frame, no storage, no
// request and no model call. Reading levels and the document format originate
// from TextFold by Xia Chen (https://github.com/chenxiachan/textfold).

export type FoldFinding = { id: string; label: string };

type Props = {
    document: TextFoldDocument;
    /** Accessible name of the reader region. */
    label?: string;
    initialLevel?: FoldLevel;
    /** Offer the document as a Textfold JSON file. */
    exportable?: boolean;
    /**
     * Set only for documents OpenPaper built itself (investigation previews):
     * paragraphs then show their attribution and findings, and a finding opens
     * at the returned address (null renders it as plain text). Imported briefs
     * never get this, so their extension fields are kept for export, not shown.
     */
    findingHref?: (id: string) => string | null;
};

export function downloadFold(doc: TextFoldDocument) {
    let serialized: string;
    try { serialized = serializeTextFold(doc); }
    catch { toast.error("Could not export this brief as Textfold. It must fit the supported format and 1 MB size limit."); return; }
    const url = URL.createObjectURL(new Blob([serialized], { type: "application/json" }));
    const anchor = window.document.createElement("a");
    anchor.href = url;
    anchor.download = `${doc.id.replace(/[^a-zA-Z0-9_-]/g, "-") || "research-brief"}.textfold.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Source Markdown never loads a remote image or runs markup: react-markdown
// drops raw HTML and unsafe URL schemes, and images become their description.
const components: Components = {
    img: ({ alt }) => <span>[Image: {alt || "source figure"}]</span>,
    // `id` carries footnote anchors. The generated describedby attribute is dropped with the
    // heading id below: both are the same in every paragraph that has a footnote.
    a: ({ href, title, id, children }) => href
        ? <a id={id} href={href} title={title} {...(href.startsWith("#") ? {} : { target: "_blank", rel: "noopener noreferrer" })}>{children}</a>
        : <span id={id} title={title}>{children}</span>,
    h2: ({ id, className, children }) => <h2 id={id === "footnote-label" ? undefined : id} className={className}>{children}</h2>,
};
const plugins = [remarkGfm];

// `prefix` keeps footnote anchors of different paragraphs apart.
const FoldMarkdown = memo(function FoldMarkdown({ text, prefix, className }: { text: string; prefix: string; className?: string }) {
    return (
        <div className={cn("prose prose-sm dark:prose-invert max-w-none break-words [overflow-wrap:anywhere] prose-p:my-1.5 prose-pre:overflow-x-auto [&_table]:block [&_table]:overflow-x-auto", className)}>
            <Markdown remarkPlugins={plugins} remarkRehypeOptions={{ clobberPrefix: `${prefix}-` }} components={components}>{text}</Markdown>
        </div>
    );
});

function scrollParent(element: HTMLElement): Element {
    for (let node = element.parentElement; node; node = node.parentElement) {
        const overflow = getComputedStyle(node).overflowY;
        if ((overflow === "auto" || overflow === "scroll") && node.scrollHeight > node.clientHeight) return node;
    }
    return window.document.scrollingElement || window.document.documentElement;
}

export function FoldedReader({ document: doc, label = "Folded reading", initialLevel = "takeaway", exportable = false, findingHref }: Props) {
    const [level, setLevel] = useState<FoldLevel>(initialLevel);
    // Paragraphs the reader opened further than the document level.
    // Keyed by document id in a Map, because ids are arbitrary strings. Locally folded text has
    // positional ids, so after an edit that shifts paragraphs the state follows the position.
    const [opened, setOpened] = useState<Map<string, FoldLevel>>(() => new Map());
    const root = useRef<HTMLDivElement>(null);
    const anchor = useRef<{ element: HTMLElement; top: number } | null>(null);
    const prefix = useId();
    const context = useMemo(() => foldContext(doc), [doc]);
    const silent = context.silent;
    const links = useMemo(() => linksFrom(doc), [doc]);
    const domIds = useMemo(() => {
        const ids = new Map<string, string>();
        doc.sections.forEach((section, i) => {
            ids.set(section.id, `${prefix}s${i}`);
            // A paragraph that only defines references is not on the page; links to it land on its section.
            section.units.forEach((unit, j) => ids.set(unit.id, context.silent.has(unit.id) ? `${prefix}s${i}` : `${prefix}u${i}-${j}`));
        });
        return ids;
    }, [doc, prefix, context]);

    // Keep the paragraph being read in place when every paragraph changes height.
    const changeLevel = (next: FoldLevel) => {
        if (next === level && !opened.size) return;
        const container = root.current;
        anchor.current = null;
        if (container && container.getBoundingClientRect().top < 0) {
            const visible = Array.from(container.querySelectorAll<HTMLElement>("[data-fold-unit]")).find(unit => unit.getBoundingClientRect().bottom > 0);
            if (visible) anchor.current = { element: visible, top: visible.getBoundingClientRect().top };
        }
        setLevel(next);
        setOpened(new Map());
    };
    useLayoutEffect(() => {
        const kept = anchor.current;
        anchor.current = null;
        if (!kept || !kept.element.isConnected) return;
        scrollParent(kept.element).scrollTop += kept.element.getBoundingClientRect().top - kept.top;
    }, [level]);

    const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        const target = event.target as HTMLElement;
        if (target.closest("input,textarea,select,[contenteditable]")) return;
        const group = target.closest("[role=radiogroup]");
        if (group && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
            const step = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
            const next = LEVEL_ORDER[(LEVEL_ORDER.indexOf(level) + step + LEVEL_ORDER.length) % LEVEL_ORDER.length];
            event.preventDefault();
            changeLevel(next);
            group.querySelector<HTMLElement>(`[data-level="${next}"]`)?.focus();
            return;
        }
        const index = Number(event.key) - 1;
        if (Number.isInteger(index) && index >= 0 && index < LEVEL_ORDER.length) { event.preventDefault(); changeLevel(LEVEL_ORDER[index]); }
    };

    const hasText = doc.sections.some(section => section.units.some(unit => !silent.has(unit.id)));
    const compact = level === "topic";

    return (
        <div ref={root} role="region" aria-label={label} tabIndex={-1} onKeyDown={onKeyDown} data-reader-ready="true" data-level={level} className="min-w-0 outline-none">
            <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 bg-background py-2">
                <div role="radiogroup" aria-label="Reading level" className="flex flex-wrap gap-1">
                    {LEVEL_ORDER.map((item, index) => (
                        <button
                            key={item}
                            type="button"
                            role="radio"
                            aria-checked={level === item}
                            aria-keyshortcuts={String(index + 1)}
                            tabIndex={level === item ? 0 : -1}
                            data-level={item}
                            onClick={() => changeLevel(item)}
                            className={cn(
                                "rounded-md px-2.5 py-1 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                                level === item
                                    ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                            )}
                        >
                            {LEVEL_LABELS[item]}
                        </button>
                    ))}
                </div>
                {exportable && (
                    <Button variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={() => downloadFold(doc)}>
                        <Download aria-hidden className="h-3.5 w-3.5" />Export Textfold
                    </Button>
                )}
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{provenanceLine(doc)}</p>

            {!hasText && <p className="mt-6 text-sm text-muted-foreground">Nothing to read here yet.</p>}
            {hasText && (
                <div className={cn("mt-6", compact ? "space-y-5" : "space-y-8")}>
                    {doc.sections.map((section, i) => {
                        const Heading = section.depth > 1 ? "h4" : "h3";
                        const topic = section.topic.trim();
                        const takeaway = section.takeaway.trim();
                        const same = (value: string) => value.toLocaleLowerCase() === section.title.trim().toLocaleLowerCase();
                        return (
                            <section key={section.id} id={domIds.get(section.id)} aria-label={section.title} className="scroll-mt-16">
                                <Heading className={cn("font-semibold leading-snug [overflow-wrap:anywhere]", section.depth > 1 ? "text-sm" : "text-base")}>{section.title}</Heading>
                                {(links.get(section.id) || []).length > 0 && (
                                    <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                                        {links.get(section.id)!.map((link, index) => <a key={index} className={action} href={`#${domIds.get(link.to)}`}>{link.rel} → {link.title}</a>)}
                                    </p>
                                )}
                                {compact && topic && !same(topic) && <p className="mt-1 text-sm text-muted-foreground">{topic}</p>}
                                {!doc.provenance.local && (level === "topic" || level === "takeaway") && takeaway && !same(takeaway) && (
                                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{takeaway}</p>
                                )}
                                {section.units.every(unit => silent.has(unit.id)) && <p className="mt-2 text-sm text-muted-foreground">No text in this section.</p>}
                                <div className={cn("mt-2", compact ? "space-y-1.5" : "space-y-4")}>
                                    {section.units.map((unit, j) => silent.has(unit.id) ? null : (
                                        <FoldUnit
                                            key={unit.id}
                                            unit={unit}
                                            domId={domIds.get(unit.id)!}
                                            path={`${i}-${j}`}
                                            name={`paragraph ${j + 1} of ${section.title}`}
                                            documentLevel={level}
                                            openedTo={opened.get(unit.id)}
                                            context={context}
                                            links={(links.get(unit.id) || []).map(link => ({ ...link, href: `#${domIds.get(link.to)}` }))}
                                            findingHref={findingHref}
                                            onOpen={next => setOpened(current => {
                                                const result = new Map(current);
                                                if (next) result.set(unit.id, next); else result.delete(unit.id);
                                                return result;
                                            })}
                                        />
                                    ))}
                                </div>
                            </section>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

type UnitProps = {
    unit: TextFoldUnit;
    domId: string;
    path: string;
    name: string;
    documentLevel: FoldLevel;
    openedTo?: FoldLevel;
    context: FoldContext;
    links: { rel: string; title: string; href: string }[];
    findingHref?: (id: string) => string | null;
    onOpen: (level: FoldLevel | null) => void;
};

const action = "rounded-sm underline-offset-2 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring";

function FoldUnit({ unit, domId, path, name, documentLevel, openedTo, context, links, findingHref, onOpen }: UnitProps) {
    const shown = unitView(unit, openedTo || documentLevel);
    const step = nextStep(unit, shown.level);
    const attribution = findingHref && typeof unit.attribution === "string" ? unit.attribution : "";
    const findings = findingHref && Array.isArray(unit.findings)
        ? unit.findings.filter((item): item is FoldFinding => !!item && typeof item === "object" && typeof item.id === "string" && typeof item.label === "string")
        : [];
    const fallThrough = !openedTo && shown.level !== documentLevel;
    // The control just used may leave the page (Show full text at Full, Fold back once folded).
    // Focus then moves to the paragraph's remaining control so the keyboard stays in the reader.
    const actions = useRef<HTMLDivElement>(null);
    const refocus = useRef(false);
    useEffect(() => {
        if (!refocus.current) return;
        refocus.current = false;
        if (!actions.current?.contains(window.document.activeElement)) actions.current?.querySelector("button")?.focus();
    }, [openedTo]);
    const open = (next: FoldLevel | null) => { refocus.current = true; onOpen(next); };
    return (
        <div id={domId} data-fold-unit={path} data-shown={shown.level} className="min-w-0 scroll-mt-16">
            {attribution && <p className="text-xs font-medium text-muted-foreground">{attribution}</p>}
            {shown.markdown.trim() ? (
                <FoldMarkdown
                    text={withReferences(context, shown.markdown)}
                    prefix={domId}
                    className={cn(shown.level === "topic" && "font-medium", shown.source && openedTo && "border-l-2 border-blue-500/40 pl-3")}
                />
            ) : <p className="text-sm text-muted-foreground">No text.</p>}
            <div ref={actions} className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                {(openedTo || fallThrough) && <span>{LEVEL_LABELS[shown.level]}{shown.source ? " · source wording" : ""}</span>}
                {step && (
                    <button type="button" className={action} aria-label={`${step === "brief" ? "Show source sentences" : "Show full text"}: ${name}`} onClick={() => open(step)}>
                        {step === "brief" ? "Show source sentences" : "Show full text"}
                    </button>
                )}
                {openedTo && <button type="button" className={action} aria-label={`Fold back: ${name}`} onClick={() => open(null)}>Fold back</button>}
                {links.map((link, index) => <a key={index} className={action} href={link.href}>{link.rel} → {link.title}</a>)}
                {findings.map((finding, index) => {
                    const href = findingHref?.(finding.id);
                    return href
                        ? <Link key={index} prefetch={false} className={cn(action, "text-blue-700 dark:text-blue-300")} href={href}>Finding: {finding.label}</Link>
                        : <span key={index}>Finding: {finding.label}</span>;
                })}
            </div>
        </div>
    );
}

"use client";

import Link from "next/link";
import { memo, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import Markdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download, FileText, Network, X } from "lucide-react";
import { FoldMap } from "./FoldMap";
import { initiallyCollapsed } from "@/lib/fold-map";
import type { MapSelection } from "./FoldMap";
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
    literalText?: boolean;
    sectionAction?: (sectionId: string) => ReactNode;
    /** Which view opens first. */
    initialView?: FoldViewMode;
    /** Shown after the text in the reading view. */
    footer?: ReactNode;
};

export type FoldViewMode = "map" | "read";

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

export function FoldedReader({ document: doc, label = "Folded reading", initialLevel = "takeaway", exportable = false, findingHref, sectionAction, literalText = false, initialView = "map", footer }: Props) {
    const [level, setLevel] = useState<FoldLevel>(initialLevel);
    const [view, setView] = useState<FoldViewMode>(initialView);
    const [selected, setSelected] = useState<MapSelection>(null);
    const [opened, setOpened] = useState<Map<string, FoldLevel>>(() => new Map());
    const root = useRef<HTMLDivElement>(null);
    const [collapsed, setCollapsed] = useState(() => initiallyCollapsed(doc));
    // The document can change under a mounted reader (a saved edit, an import, typing in a
    // draft). When its structure changes, state keyed by its ids no longer means the same
    // paragraphs, so it starts again; edits inside a paragraph keep it.
    const structure = useMemo(() => doc.id + "\n" + doc.sections.map(section => section.id + "\t" + section.units.map(unit => unit.id).join("\t")).join("\n"), [doc]);
    const [seen, setSeen] = useState(structure);
    if (seen !== structure) {
        setSeen(structure);
        setCollapsed(initiallyCollapsed(doc));
        setSelected(null);
        setOpened(new Map());
    }
    const detail = useRef<HTMLDivElement>(null);
    // Selecting on the map moves focus to the paragraph's text; closing it returns to its node.
    const select = (next: MapSelection) => {
        const node = next ? null : root.current?.querySelector<HTMLElement>('[data-map-node][aria-pressed="true"]');
        setSelected(next);
        if (next) requestAnimationFrame(() => detail.current?.focus({ preventScroll: true }));
        else (node || root.current)?.focus({ preventScroll: true });
    };
    // A paragraph to bring into view once the reading view has rendered.
    const [reveal, setReveal] = useState<string | null>(null);
    // Paragraphs the reader opened further than the document level.
    // Keyed by document id in a Map, because ids are arbitrary strings. Locally folded text has
    // positional ids, so after an edit that shifts paragraphs the state follows the position.
    const body = useRef<HTMLDivElement>(null);
    const anchor = useRef<{ element: HTMLElement; top: number } | null>(null);
    const prefix = useId();
    const context = useMemo(() => foldContext(doc, literalText), [doc, literalText]);
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
        const container = body.current;
        anchor.current = null;
        if (container && container.scrollTop > 0) {
            const top = container.getBoundingClientRect().top;
            const visible = Array.from(container.querySelectorAll<HTMLElement>("[data-fold-unit]")).find(unit => unit.getBoundingClientRect().bottom > top);
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

    useEffect(() => {
        if (view !== "read" || !reveal) return;
        const target = window.document.getElementById(reveal);
        setReveal(null);
        if (!target) return;
        target.scrollIntoView({ block: "start" });
        // A paragraph already shown in full has no control of its own; the reader keeps focus then.
        (target.querySelector<HTMLElement>("button") || root.current)?.focus({ preventScroll: true });
    }, [view, reveal]);

    // The paragraph or finding picked on the map, looked up in the current document.
    const picked = useMemo(() => {
        if (!selected) return null;
        for (let i = 0; i < doc.sections.length; i++) {
            const section = doc.sections[i];
            for (let j = 0; j < section.units.length; j++) {
                const unit = section.units[j];
                if (selected.kind === "unit" && unit.id === selected.ref) return { kind: "unit" as const, section, unit, i, j };
                if (selected.kind === "finding" && Array.isArray(unit.findings)) {
                    const finding = (unit.findings as FoldFinding[]).find(item => item && item.id === selected.ref);
                    if (finding) return { kind: "finding" as const, finding };
                }
            }
        }
        return null;
    }, [doc, selected]);
    const openOf = (id: string) => (next: FoldLevel | null) => setOpened(current => {
        const result = new Map(current);
        if (next) result.set(id, next); else result.delete(id);
        return result;
    });

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
    const linkCount = (doc.links || []).length;

    return (
        <div ref={root} role="region" aria-label={label} tabIndex={-1} onKeyDown={onKeyDown} data-reader-ready="true" data-level={level} data-view={view} className="flex h-full min-h-0 min-w-0 flex-col outline-none">
            <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b px-3 py-2">
                <div role="group" aria-label="View" className="flex rounded-lg border p-0.5">
                    {([["map", "Map", Network], ["read", "Read", FileText]] as const).map(([item, name, Icon]) => (
                        <button
                            key={item}
                            type="button"
                            aria-pressed={view === item}
                            data-view-option={item}
                            onClick={() => setView(item)}
                            className={cn(
                                "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                                view === item ? "bg-blue-600 text-white dark:bg-blue-500" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                            )}
                        >
                            <Icon aria-hidden className="h-3.5 w-3.5" />{name}
                        </button>
                    ))}
                </div>
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
                    <Button variant="ghost" size="sm" className="ml-auto h-7 gap-1.5 px-2 text-xs" onClick={() => downloadFold(doc)}>
                        <Download aria-hidden className="h-3.5 w-3.5" />Export Textfold
                    </Button>
                )}
            </div>

            {!hasText && <p className="p-4 text-sm text-muted-foreground">Nothing to read here yet.</p>}

            {hasText && view === "map" && (
                <>
                    <FoldMap key={structure} document={doc} level={level} context={context} findings={!!findingHref} collapsed={collapsed} onCollapsed={setCollapsed} selected={picked ? selected : null} onSelect={select} className="flex-1" />
                    <div ref={detail} tabIndex={-1} role="group" aria-label={picked ? "Selected on the map" : "Map guide"} className="max-h-[45%] shrink-0 overflow-y-auto border-t px-4 py-3 outline-none" data-map-detail={picked ? picked.kind : "none"}>
                        <p className="mb-1.5 text-[11px] leading-4 text-muted-foreground">{provenanceLine(doc)}</p>
                        {!picked && (
                            <p className="text-xs leading-5 text-muted-foreground">
                                Select a paragraph to read it here. Sections fold and unfold.
                                {linkCount > 0 && " Dashed arrows are argument links."}
                                {findingHref && " Green nodes are the findings paragraphs cite."}
                            </p>
                        )}
                        {picked?.kind === "unit" && (
                            <>
                                <div className="mb-1.5 flex items-start justify-between gap-3">
                                    <p className="min-w-0 text-xs font-medium text-muted-foreground [overflow-wrap:anywhere]">{picked.section.title} · paragraph {picked.j + 1}</p>
                                    <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                                        <button type="button" className={action} onClick={() => { setReveal(domIds.get(picked.unit.id) || null); setView("read"); }}>Read in context</button>
                                        <button type="button" className={action} aria-label="Close paragraph" onClick={() => select(null)}><X aria-hidden className="h-3.5 w-3.5" /></button>
                                    </div>
                                </div>
                                {sectionAction?.(picked.section.id)}
                                <FoldUnit
                                    key={picked.unit.id}
                                    unit={picked.unit}
                                    domId={`${prefix}detail`}
                                    name={`paragraph ${picked.j + 1} of ${picked.section.title}`}
                                    documentLevel={level}
                                    openedTo={opened.get(picked.unit.id)}
                                    context={context}
                                    links={[]}
                                    findingHref={findingHref}
                                    onOpen={openOf(picked.unit.id)}
                                />
                            </>
                        )}
                        {picked?.kind === "finding" && (
                            <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <p className="text-xs font-medium text-muted-foreground">Finding</p>
                                    <p className="mt-1 text-sm [overflow-wrap:anywhere]">{picked.finding.label}</p>
                                    {findingHref?.(picked.finding.id) && (
                                        <Link prefetch={false} className={cn(action, "mt-1 inline-block text-xs text-blue-700 dark:text-blue-300")} href={findingHref(picked.finding.id)!}>Open in Evidence</Link>
                                    )}
                                </div>
                                <button type="button" className={cn(action, "text-muted-foreground")} aria-label="Close finding" onClick={() => select(null)}><X aria-hidden className="h-3.5 w-3.5" /></button>
                            </div>
                        )}
                    </div>
                </>
            )}

            {view === "read" && (
                <div ref={body} className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
                    <p className="text-xs leading-5 text-muted-foreground">{provenanceLine(doc)}</p>
                    {hasText && (
                        <div className={cn("mt-5", compact ? "space-y-5" : "space-y-8")}>
                            {doc.sections.map((section, i) => {
                                const Heading = section.depth > 1 ? "h4" : "h3";
                                const topic = section.topic.trim();
                                const takeaway = section.takeaway.trim();
                                const same = (value: string) => value.toLocaleLowerCase() === section.title.trim().toLocaleLowerCase();
                                return (
                                    <section key={section.id} id={domIds.get(section.id)} aria-label={section.title} className="scroll-mt-2">
                                        <Heading className={cn("font-semibold leading-snug [overflow-wrap:anywhere]", section.depth > 1 ? "text-sm" : "text-base")}>{section.title}</Heading>
                                        {sectionAction?.(section.id)}
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
                                                    onOpen={openOf(unit.id)}
                                                />
                                            ))}
                                        </div>
                                    </section>
                                );
                            })}
                        </div>
                    )}
                    {footer && <div className="mt-8">{footer}</div>}
                </div>
            )}
        </div>
    );
}

type UnitProps = {
    unit: TextFoldUnit;
    domId: string;
    /** Position in the reading view; absent in the map's detail pane. */
    path?: string;
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
        <div id={domId} data-fold-unit={path} data-shown={shown.level} className="min-w-0 scroll-mt-2">
            {attribution && <p className="text-xs font-medium text-muted-foreground">{attribution}</p>}
            {context.literal && shown.markdown ? (
                <p className="whitespace-pre-wrap break-words text-sm">{shown.markdown}</p>
            ) : shown.markdown.trim() ? (
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

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import {
    AlertTriangle,
    ArrowDown,
    ArrowUp,
    CheckCircle2,
    ChevronDown,
    CircleDashed,
    FileText,
    NotebookPen,
    PenLine,
    Plus,
    Quote,
    Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Block, Investigation } from "@/lib/investigation";
import { quotation } from "@/lib/investigation-preview";
import { Button } from "@/components/ui/button";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";
import { useInvestigation } from "@/components/project/InvestigationProvider";
import { DraftAssistant } from "@/components/project/DraftAssistant";
import { EmptyState, FoldedPreview, ProseField, ViewFrame, newId, useCanEdit } from "./shared";

const STARTER_SECTIONS = [
    "Introduction",
    "Related work",
    "Evidence and reconciliation",
    "Proposed experiment",
    "Limitations",
    "Conclusion",
];

const PROVENANCE: Record<Block["provenance"]["kind"], string> = {
    human: "Human-written",
    assembled: "Assembled from source",
    assistant: "AI-authored — review required",
    imported: "Imported — unverified origin",
};

// The review step between choosing evidence and inserting a block. Only one
// can be open at a time for the whole manuscript.
type Manual = { sectionId: string; text: string; kind: "paragraph" | "source_quote"; findingIds: string[] };

export function DraftView() {
    const { projectId } = useProjectWorkspace();
    const { document: doc, update, save, validation, loaded, status } = useInvestigation();
    const canEdit = useCanEdit();
    const params = useSearchParams();
    const lastFocused = useRef("");

    // One claim/finding selection is shared by every section's picker.
    const [selected, setSelected] = useState<string[]>([]);
    const [draftClaims, setDraftClaims] = useState<string[]>([]);
    const [manual, setManual] = useState<Manual | null>(null);
    // Explicit open/closed choices for each section's "Add to section" area.
    const [addOpen, setAddOpen] = useState<Record<string, boolean>>({});
    const [autoOpened, setAutoOpened] = useState<string | null>(null);

    const sections = doc.manuscript.sections;
    const blockCount = sections.reduce((total, section) => total + section.blocks.length, 0);
    const reviewCount = sections.reduce(
        (total, section) => total + section.blocks.filter(block => validation.blocks[block.id] === "review_needed").length,
        0,
    );

    // An empty manuscript starts with the first section ready to write into.
    // The choice is remembered so the area does not snap shut after the first
    // block is inserted.
    const firstSectionId = sections[0]?.id ?? null;
    if (loaded && firstSectionId && blockCount === 0 && autoOpened !== firstSectionId) setAutoOpened(firstSectionId);

    useEffect(() => {
        const id = params.get("block");
        const valid = sections.some(section => section.blocks.some(block => block.id === id));
        if (id && valid && lastFocused.current !== id) {
            window.document.getElementById("block-" + id)?.scrollIntoView({ block: "start" });
            lastFocused.current = id;
        }
    }, [params, sections]);

    // Keep selections in document order, as the manuscript stores them.
    const toggleFinding = (id: string, on: boolean) =>
        setSelected(previous => doc.findings.map(finding => finding.id).filter(item => (item === id ? on : previous.includes(item))));
    const toggleClaim = (id: string, on: boolean) =>
        setDraftClaims(previous => doc.claims.map(claim => claim.id).filter(item => (item === id ? on : previous.includes(item))));

    function createDraft() {
        update(d => {
            d.manuscript.sections = STARTER_SECTIONS.map(title => ({ id: newId(), title, blocks: [] }));
        });
    }

    function moveSection(index: number, offset: -1 | 1) {
        update(d => {
            const list = d.manuscript.sections;
            [list[index + offset], list[index]] = [list[index], list[index + offset]];
        });
    }

    function insertManual() {
        if (!manual) return;
        update(d => {
            d.manuscript.sections.find(section => section.id === manual.sectionId)?.blocks.push({
                id: newId(),
                kind: manual.kind,
                text: manual.text,
                claim_ids: draftClaims,
                finding_ids: manual.findingIds,
                provenance: { kind: manual.kind === "source_quote" ? "assembled" : "human" },
                dependency_pins: {},
            });
        });
        setManual(null);
    }

    return (
        <ViewFrame>
            <header className="space-y-2">
                <h1 className="text-2xl font-bold tracking-tight">Write</h1>
                <p className="text-sm leading-6 text-muted-foreground">
                    The manuscript, written section by section. Every paragraph keeps its authorship and the evidence it cites.
                </p>
                {loaded && sections.length > 0 && (
                    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        <span>
                            {sections.length} {sections.length === 1 ? "section" : "sections"} · {blockCount} {blockCount === 1 ? "block" : "blocks"}
                        </span>
                        {reviewCount > 0 && (
                            <span className="inline-flex items-center gap-1 font-medium text-yellow-700 dark:text-yellow-400">
                                <AlertTriangle aria-hidden className="h-3.5 w-3.5 shrink-0" />
                                {reviewCount} with changed evidence
                            </span>
                        )}
                    </p>
                )}
            </header>

            {!loaded && (
                <p className="text-sm text-muted-foreground">
                    {status === "Loading" ? "Loading the manuscript…" : "The manuscript has not loaded, so it cannot be edited yet."}
                </p>
            )}

            <fieldset disabled={!loaded || status === "Saving"} className="min-w-0 space-y-10">
                <ProseField
                    label="Manuscript title"
                    size="title"
                    maxLength={500}
                    placeholder="Untitled manuscript"
                    value={doc.manuscript.title}
                    onChange={value => update(d => { d.manuscript.title = value; })}
                />

                {sections.length > 1 && (
                    <nav aria-label="Manuscript outline">
                        <p className="text-xs font-medium text-muted-foreground">Outline</p>
                        <ol className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                            {sections.map((section, index) => (
                                <li key={section.id} className="min-w-0 max-w-full">
                                    <a
                                        href={"#section-" + section.id}
                                        className="inline-flex max-w-full items-baseline gap-1.5 rounded-sm text-blue-600 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:text-blue-400"
                                    >
                                        <span className="text-xs tabular-nums text-muted-foreground">{index + 1}</span>
                                        <span className="truncate">{section.title || "Untitled section"}</span>
                                    </a>
                                </li>
                            ))}
                        </ol>
                    </nav>
                )}

                {loaded && sections.length === 0 && (
                    <EmptyState icon={NotebookPen} title="No draft yet">
                        {canEdit ? (
                            <>
                                <p>
                                    Start from a standard paper outline — {STARTER_SECTIONS.join(", ")}. Every section can be renamed and reordered.
                                </p>
                                <Button type="button" onClick={createDraft}>
                                    <PenLine aria-hidden className="h-4 w-4" />
                                    Create draft
                                </Button>
                            </>
                        ) : (
                            <p>The project editors have not started the manuscript.</p>
                        )}
                    </EmptyState>
                )}

                {sections.map((section, index) => {
                    const open = addOpen[section.id] ?? section.id === autoOpened;
                    // Once opened the area stays mounted (hidden) so an assistant
                    // request or proposal in it survives collapsing.
                    const mounted = open || section.id in addOpen;
                    const panelId = "add-" + section.id;

                    return (
                        <section key={section.id} id={"section-" + section.id} className="min-w-0 scroll-mt-6 space-y-5">
                            <div className="flex items-start gap-1 border-b pb-1">
                                <span aria-hidden className="mt-2.5 w-6 shrink-0 text-sm tabular-nums text-muted-foreground">{index + 1}</span>
                                <ProseField
                                    label="Section title"
                                    hideLabel
                                    size="lead"
                                    maxLength={500}
                                    placeholder="Untitled section"
                                    // Padding cancels the field's negative margin so it
                                    // does not slide under the number and the buttons.
                                    className="flex-1 px-2"
                                    inputClassName="text-lg font-semibold"
                                    value={section.title}
                                    onChange={value => update(d => { d.manuscript.sections[index].title = value; })}
                                />
                                {canEdit && (
                                    <div className="mt-1 flex shrink-0">
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="icon"
                                            className="size-8 text-muted-foreground"
                                            aria-label="Move section up"
                                            disabled={index === 0}
                                            onClick={() => moveSection(index, -1)}
                                        >
                                            <ArrowUp aria-hidden className="h-4 w-4" />
                                        </Button>
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="icon"
                                            className="size-8 text-muted-foreground"
                                            aria-label="Move section down"
                                            disabled={index === sections.length - 1}
                                            onClick={() => moveSection(index, 1)}
                                        >
                                            <ArrowDown aria-hidden className="h-4 w-4" />
                                        </Button>
                                    </div>
                                )}
                            </div>

                            {section.blocks.length === 0 && (
                                <p className="text-sm text-muted-foreground">Nothing written in this section yet.</p>
                            )}

                            {section.blocks.map((block, blockIndex) => (
                                <ManuscriptBlock
                                    key={block.id}
                                    doc={doc}
                                    block={block}
                                    projectId={projectId}
                                    state={validation.blocks[block.id]}
                                    onText={value => update(d => { d.manuscript.sections[index].blocks[blockIndex].text = value; })}
                                    onReviewed={canEdit ? () => void save([block.id]) : undefined}
                                />
                            ))}

                            {canEdit && (
                                <div className="space-y-3">
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        className="-ml-2 text-muted-foreground"
                                        aria-expanded={open}
                                        aria-controls={mounted ? panelId : undefined}
                                        onClick={() => setAddOpen(previous => ({ ...previous, [section.id]: !open }))}
                                    >
                                        {open ? <ChevronDown aria-hidden className="h-4 w-4" /> : <Plus aria-hidden className="h-4 w-4" />}
                                        Add to section
                                    </Button>

                                    {mounted && (
                                        <div id={panelId} hidden={!open} className="space-y-5 rounded-lg bg-muted/40 p-4">
                                            <div>
                                                <p className="text-sm font-medium">Add to this section</p>
                                                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                                                    Choose what the next paragraph argues and rests on. The selection is shared across sections.
                                                </p>
                                            </div>

                                            <div className="grid min-w-0 gap-5 md:grid-cols-2">
                                                <CheckGroup
                                                    legend="Claims for the next paragraph"
                                                    options={doc.claims.map(claim => ({ id: claim.id, label: claim.statement || "Untitled claim" }))}
                                                    selected={draftClaims}
                                                    onToggle={toggleClaim}
                                                    empty={<>No claims yet. Add them in the <Link className="underline underline-offset-2" href={`/projects/${projectId}`}>overview</Link>.</>}
                                                />
                                                <CheckGroup
                                                    legend="Evidence for the next paragraph"
                                                    options={doc.findings.map(finding => ({ id: finding.id, label: finding.label || "Untitled finding" }))}
                                                    selected={selected}
                                                    onToggle={toggleFinding}
                                                    empty={<>No findings yet. Attach them in <Link className="underline underline-offset-2" href={`/projects/${projectId}/evidence`}>Evidence</Link>.</>}
                                                />
                                            </div>

                                            <div className="space-y-2">
                                                <div className="flex flex-wrap gap-2">
                                                    <Button
                                                        type="button"
                                                        size="sm"
                                                        onClick={() => setManual({ sectionId: section.id, text: "", kind: "paragraph", findingIds: [...selected] })}
                                                    >
                                                        <PenLine aria-hidden className="h-4 w-4" />
                                                        Insert editable paragraph
                                                    </Button>
                                                    <Button
                                                        type="button"
                                                        variant="outline"
                                                        size="sm"
                                                        disabled={selected.length !== 1}
                                                        onClick={() => setManual({ sectionId: section.id, text: "", kind: "source_quote", findingIds: [...selected] })}
                                                    >
                                                        <Quote aria-hidden className="h-4 w-4" />
                                                        Prepare source quote
                                                    </Button>
                                                    <Button
                                                        type="button"
                                                        variant="outline"
                                                        size="sm"
                                                        onClick={() => update(d => {
                                                            d.manuscript.sections[index].blocks.push({
                                                                id: newId(),
                                                                kind: "gap",
                                                                text: "Evidence needed",
                                                                claim_ids: [],
                                                                finding_ids: [],
                                                                provenance: { kind: "human" },
                                                                dependency_pins: {},
                                                            });
                                                        })}
                                                    >
                                                        <CircleDashed aria-hidden className="h-4 w-4" />
                                                        Insert evidence gap
                                                    </Button>
                                                </div>
                                                <p className="text-xs leading-5 text-muted-foreground">
                                                    {selected.length} {selected.length === 1 ? "finding" : "findings"} and {draftClaims.length} {draftClaims.length === 1 ? "claim" : "claims"} selected. A source quote needs exactly one finding.
                                                </p>
                                            </div>

                                            <DraftAssistant sectionId={section.id} findingIds={selected} claimIds={draftClaims} />
                                        </div>
                                    )}
                                </div>
                            )}

                            {canEdit && manual?.sectionId === section.id && (
                                <div className="space-y-4 rounded-lg bg-blue-50 p-4 dark:bg-blue-950/40">
                                    <div>
                                        <p className="text-sm font-medium">
                                            {manual.kind === "paragraph" ? "New paragraph" : "New source quote"}
                                        </p>
                                        <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                            Review selected evidence before inserting. {manual.findingIds.length} findings selected.
                                        </p>
                                    </div>
                                    {manual.findingIds.length > 0 && (
                                        <ul className="flex flex-wrap gap-1.5">
                                            {manual.findingIds.map(id => (
                                                <li key={id} className="max-w-full truncate rounded-md bg-background px-2 py-0.5 text-xs">
                                                    {doc.findings.find(finding => finding.id === id)?.label || "Untitled finding"}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                    {manual.kind === "paragraph" ? (
                                        <ProseField
                                            label="Paragraph proposal"
                                            maxLength={10000}
                                            placeholder="Write the paragraph. You can keep editing it after it is inserted."
                                            inputClassName="min-h-24 border-input bg-background hover:bg-background"
                                            value={manual.text}
                                            onChange={text => setManual({ ...manual, text })}
                                        />
                                    ) : (
                                        <p className="flex items-start gap-2 text-sm leading-6">
                                            <Quote aria-hidden className="mt-1 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
                                            {doc.findings.find(finding => finding.id === manual.findingIds[0])?.source.kind === "anchored"
                                                ? "The saved verified quotation will be used."
                                                : "A current accessible quotation is required."}
                                        </p>
                                    )}
                                    <div className="flex flex-wrap gap-2">
                                        <Button type="button" size="sm" onClick={insertManual}>Insert paragraph</Button>
                                        <Button type="button" variant="ghost" size="sm" onClick={() => setManual(null)}>Cancel insertion</Button>
                                    </div>
                                </div>
                            )}
                        </section>
                    );
                })}

                {canEdit && sections.length > 0 && (
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => update(d => { d.manuscript.sections.push({ id: newId(), title: "Untitled section", blocks: [] }); })}
                    >
                        <Plus aria-hidden className="h-4 w-4" />
                        Add section
                    </Button>
                )}
            </fieldset>

            <FoldedPreview view="draft" />
        </ViewFrame>
    );
}

interface ManuscriptBlockProps {
    doc: Investigation;
    block: Block;
    projectId: string;
    // Server validation of the saved block; absent until it has been saved.
    state?: string;
    onText: (value: string) => void;
    // Editors only: acknowledge that the cited evidence changed.
    onReviewed?: () => void;
}

function ManuscriptBlock({ doc, block, projectId, state, onText, onReviewed }: ManuscriptBlockProps) {
    const assistant = block.provenance.kind === "assistant";

    return (
        <article id={"block-" + block.id} className="min-w-0 scroll-mt-6 space-y-2">
            {block.kind === "source_quote" ? (
                <div className="flex gap-3 border-l-2 border-blue-500 py-1 pl-4 dark:border-blue-400">
                    <Quote aria-hidden className="mt-1.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
                    <blockquote className="min-w-0 whitespace-pre-wrap break-words text-base leading-7">{quotation(doc, block)}</blockquote>
                </div>
            ) : block.kind === "gap" ? (
                <div className="rounded-md border border-dashed border-yellow-600/60 px-3 pb-1 pt-2 dark:border-yellow-400/50">
                    <p className="inline-flex items-center gap-1 text-xs font-medium text-yellow-700 dark:text-yellow-400">
                        <CircleDashed aria-hidden className="h-3.5 w-3.5 shrink-0" />
                        Gap
                    </p>
                    <ProseField
                        label="Evidence gap"
                        hideLabel
                        maxLength={10000}
                        placeholder="What evidence is missing here?"
                        value={block.text}
                        onChange={onText}
                    />
                </div>
            ) : (
                <ProseField
                    label="Paragraph"
                    hideLabel
                    size="lead"
                    maxLength={10000}
                    placeholder="Write this paragraph…"
                    value={block.text}
                    onChange={onText}
                />
            )}

            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span className={cn("inline-flex items-center gap-1", assistant && "font-medium text-foreground")}>
                    {assistant && <Sparkles aria-hidden className="h-3.5 w-3.5 shrink-0 text-blue-600 dark:text-blue-400" />}
                    {PROVENANCE[block.provenance.kind] || block.provenance.kind}
                </span>
                {block.provenance.edited && <span>human edited</span>}
                {state === "review_needed" ? (
                    <span className="inline-flex items-center gap-1 font-medium text-yellow-700 dark:text-yellow-400">
                        <AlertTriangle aria-hidden className="h-3.5 w-3.5 shrink-0" />
                        Evidence changed — review needed
                    </span>
                ) : state === "current" ? (
                    <span className="inline-flex items-center gap-1">
                        <CheckCircle2 aria-hidden className="h-3.5 w-3.5 shrink-0" />
                        Saved evidence pins
                    </span>
                ) : (
                    <span className="inline-flex items-center gap-1">
                        <CircleDashed aria-hidden className="h-3.5 w-3.5 shrink-0" />
                        Unsaved
                    </span>
                )}
            </p>

            {block.finding_ids.length > 0 && (
                <ul className="flex flex-wrap gap-1.5" aria-label="Cited findings">
                    {block.finding_ids.map(id => (
                        <li key={id} className="min-w-0 max-w-full">
                            <Link
                                href={`/projects/${projectId}/evidence?finding=${id}&block=${block.id}`}
                                className="inline-flex max-w-full items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 outline-none transition-colors hover:bg-blue-100 focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-blue-950 dark:text-blue-300 dark:hover:bg-blue-900"
                            >
                                <FileText aria-hidden className="h-3 w-3 shrink-0" />
                                <span className="truncate">{doc.findings.find(finding => finding.id === id)?.label || "Missing finding"}</span>
                            </Link>
                        </li>
                    ))}
                </ul>
            )}

            {state === "review_needed" && onReviewed && (
                <Button type="button" variant="outline" size="sm" onClick={onReviewed}>
                    <CheckCircle2 aria-hidden className="h-4 w-4" />
                    Reviewed changed evidence
                </Button>
            )}
        </article>
    );
}

interface CheckGroupProps {
    legend: string;
    options: { id: string; label: string }[];
    selected: string[];
    onToggle: (id: string, on: boolean) => void;
    empty: ReactNode;
}

// A labelled checkbox group; each checkbox is named by its option label alone.
function CheckGroup({ legend, options, selected, onToggle, empty }: CheckGroupProps) {
    return (
        <fieldset className="min-w-0">
            <legend className="text-xs font-medium text-muted-foreground">{legend}</legend>
            {options.length === 0 ? (
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{empty}</p>
            ) : (
                <ul className="-mx-1 mt-2 max-h-56 space-y-0.5 overflow-y-auto">
                    {options.map(option => (
                        <li key={option.id}>
                            <label className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1 text-sm leading-5 hover:bg-muted has-[:focus-visible]:bg-muted">
                                <input
                                    type="checkbox"
                                    className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600 dark:accent-blue-400"
                                    checked={selected.includes(option.id)}
                                    onChange={event => onToggle(option.id, event.target.checked)}
                                />
                                <span className="line-clamp-3 min-w-0 [overflow-wrap:anywhere]">{option.label}</span>
                            </label>
                        </li>
                    ))}
                </ul>
            )}
        </fieldset>
    );
}

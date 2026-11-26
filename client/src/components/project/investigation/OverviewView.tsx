"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Archive, ArchiveRestore, ArrowDown, ArrowRight, ArrowUp, Check, ChevronDown, FlaskConical, Lightbulb, MoreHorizontal, Plus, RefreshCcw, Swords } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { legacyCase } from "@/lib/investigation-preview";
import type { Claim, Investigation } from "@/lib/investigation";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";
import { useInvestigation } from "@/components/project/InvestigationProvider";
import { FoldedPreview, ProseField, RELATION_KINDS, RelationTag, SectionHeading, ViewFrame, newId, useCanEdit } from "./shared";

type CaseKey = Exclude<keyof Investigation["case"], "search_date">;

// Where the investigation stands today: the four statements a returning
// researcher needs before deciding what to do next.
const POSITION: { key: CaseKey; label: string; placeholder: string; icon: LucideIcon }[] = [
    { key: "provisional_answer", label: "Provisional answer", placeholder: "What do you currently believe, and how firmly?", icon: Lightbulb },
    { key: "unresolved_tension", label: "Unresolved tension", placeholder: "Which findings pull against each other?", icon: Swords },
    { key: "discriminating_experiment", label: "Discriminating experiment", placeholder: "What test would separate the competing explanations?", icon: FlaskConical },
    { key: "update_criteria", label: "Update criteria", placeholder: "What result would change the answer?", icon: RefreshCcw },
];

const BACKGROUND: { key: CaseKey; label: string; hint: string; placeholder: string }[] = [
    { key: "why_it_matters", label: "Why it matters", hint: "What resolving the question would change.", placeholder: "Who needs this answer, and what would they do differently?" },
    { key: "landscape", label: "Landscape", hint: "The closest existing work and how it relates.", placeholder: "Which papers come closest to answering this?" },
    { key: "coverage_limits", label: "Coverage limits", hint: "What the search did not cover. Missing evidence is not counterevidence.", placeholder: "Which venues, dates or methods were not searched?" },
    { key: "reconciliation", label: "Reconciliation", hint: "Your reading of why the findings disagree. Interpretation, not a source result.", placeholder: "Which setup differences could explain the disagreement?" },
];

// `before` and `after` are the document indexes of the neighbouring claims on
// screen, so a move is always visible even when archived claims are hidden.
function ClaimRow({ claim, index, before, after, startOpen }: { claim: Claim; index: number; before?: number; after?: number; startOpen: boolean }) {
    const { projectId } = useProjectWorkspace();
    const { document: doc, update } = useInvestigation();
    const canEdit = useCanEdit();
    const [open, setOpen] = useState(startOpen);
    const relations = doc.relations.filter(relation => relation.claim_id === claim.id);
    const swap = (other: number) => update(draft => { [draft.claims[other], draft.claims[index]] = [draft.claims[index], draft.claims[other]]; });

    return (
        <li id={`claim-${claim.id}`} className={cn("scroll-mt-4 py-4", claim.archived && "opacity-60")}>
            <div className="flex items-start gap-3">
                <span aria-hidden className="mt-2 w-5 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{index + 1}</span>
                <div className="min-w-0 flex-1">
                    <ProseField label="Claim statement" hideLabel maxLength={2000} size="lead" inputClassName="font-medium" value={claim.statement}
                        placeholder="State one claim the evidence should support or refute."
                        onChange={value => update(draft => { draft.claims[index].statement = value; })} />
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
                        {relations.length ? (
                            <Link href={`/projects/${projectId}/evidence?claim=${claim.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-ring">
                                {RELATION_KINDS.map(kind => {
                                    const count = relations.filter(relation => relation.relation === kind).length;
                                    return count ? <RelationTag key={kind} relation={kind} count={count} /> : null;
                                })}
                                <span className="sr-only">View the evidence for this claim</span>
                            </Link>
                        ) : (
                            <span className="text-xs text-muted-foreground">No evidence linked yet</span>
                        )}
                        {claim.archived && <span className="text-xs font-medium text-muted-foreground">Archived</span>}
                        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
                            className="inline-flex items-center gap-1 rounded-sm text-xs text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                            <ChevronDown aria-hidden className={cn("h-3.5 w-3.5 transition-transform motion-reduce:transition-none", open && "rotate-180")} />
                            Reasoning and caveats
                        </button>
                    </div>
                    {open && (
                        <div className="mt-3 grid gap-4 sm:grid-cols-2">
                            <ProseField label="Reasoning" placeholder="Why does the evidence lead here?" value={claim.reasoning}
                                onChange={value => update(draft => { draft.claims[index].reasoning = value; })} />
                            <ProseField label="Caveats" placeholder="Where might this claim fail?" value={claim.caveats}
                                onChange={value => update(draft => { draft.claims[index].caveats = value; })} />
                        </div>
                    )}
                </div>
                {canEdit && (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" aria-label={`Claim ${index + 1} actions`}>
                                <MoreHorizontal className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem disabled={before == null} onSelect={() => before != null && swap(before)}><ArrowUp className="h-4 w-4" />Move up</DropdownMenuItem>
                            <DropdownMenuItem disabled={after == null} onSelect={() => after != null && swap(after)}><ArrowDown className="h-4 w-4" />Move down</DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => update(draft => { draft.claims[index].archived = !claim.archived; })}>
                                {claim.archived ? <><ArchiveRestore className="h-4 w-4" />Restore</> : <><Archive className="h-4 w-4" />Archive</>}
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                )}
            </div>
        </li>
    );
}

// The shortest path to a first drafted paragraph, derived from what the
// project already contains. It disappears once every step has happened.
function NextStep({ focusQuestion, addClaim }: { focusQuestion: () => void; addClaim: () => void }) {
    const { projectId, papers, isPapersLoading, openAddPapers } = useProjectWorkspace();
    const { document: doc } = useInvestigation();
    const base = `/projects/${projectId}`;
    const drafted = doc.manuscript.sections.some(section => section.blocks.some(block => block.kind !== "gap"));
    const steps: { label: string; done: boolean; detail: string; action: { label: string; href?: string; run?: () => void } }[] = [
        { label: "State the question", done: !!doc.case.question.trim(), detail: "Start with the disputed question this project should resolve.", action: { label: "Write the question", run: focusQuestion } },
        { label: "Add a paper", done: papers.length > 0 || isPapersLoading, detail: "Add the closest related work and the papers whose findings conflict.", action: { label: "Add papers", run: () => openAddPapers() } },
        { label: "Capture a finding", done: doc.findings.length > 0, detail: "Select an exact passage and record what the source observed, separately from how you read it.", action: { label: "Go to Evidence", href: `${base}/evidence` } },
        doc.claims.length
            ? { label: "Link it to a claim", done: doc.relations.length > 0, detail: "Say whether a finding supports, challenges or qualifies one of your claims.", action: { label: "Link evidence", href: `${base}/evidence` } }
            : { label: "Link it to a claim", done: false, detail: "Add the first claim the evidence should support or refute.", action: { label: "Add a claim", run: addClaim } },
        { label: "Draft a paragraph", done: drafted, detail: "Turn linked evidence into a cited paragraph of the manuscript.", action: { label: "Go to Write", href: `${base}/draft` } },
    ];
    const next = steps.find(step => !step.done);
    if (!next) return null;

    return (
        <section aria-labelledby="next-step-heading" className="rounded-xl bg-blue-50 p-4 dark:bg-blue-950/40 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
                <div className="min-w-0 flex-1 basis-64">
                    <h2 id="next-step-heading" className="text-sm font-semibold">Next: {next.label.toLowerCase()}</h2>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{next.detail}</p>
                </div>
                {next.action.href
                    ? <Button asChild size="sm"><Link href={next.action.href}>{next.action.label}<ArrowRight aria-hidden className="h-4 w-4" /></Link></Button>
                    : <Button size="sm" onClick={next.action.run}>{next.action.label}<ArrowRight aria-hidden className="h-4 w-4" /></Button>}
            </div>
            <ol className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-xs">
                {steps.map((step, index) => (
                    <li key={step.label} aria-current={step === next ? "step" : undefined}
                        className={cn("inline-flex items-center gap-1.5", step.done ? "text-muted-foreground" : step === next ? "font-medium text-blue-700 dark:text-blue-300" : "text-muted-foreground/70")}>
                        {step.done
                            ? <Check aria-hidden className="h-3.5 w-3.5" />
                            : <span aria-hidden className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border text-[9px] leading-none">{index + 1}</span>}
                        {step.label}<span className="sr-only">{step.done ? " (done)" : ""}</span>
                    </li>
                ))}
            </ol>
        </section>
    );
}

export function OverviewView() {
    const { project, papers, isProjectLoading, projectError } = useProjectWorkspace();
    const { document: doc, update, status, loaded } = useInvestigation();
    const canEdit = useCanEdit();
    const params = useSearchParams();
    const linkedClaim = params.get("claim");
    const lastFocused = useRef("");
    const added = useRef(new Set<string>());
    const [showArchived, setShowArchived] = useState(false);

    // Deep links from Evidence and Write land on the claim they name.
    useEffect(() => {
        if (linkedClaim && lastFocused.current !== linkedClaim && doc.claims.some(claim => claim.id === linkedClaim)) {
            window.document.getElementById(`claim-${linkedClaim}`)?.scrollIntoView({ block: "start" });
            lastFocused.current = linkedClaim;
        }
    }, [linkedClaim, doc.claims]);

    const focusQuestion = () => window.document.getElementById("case-question")?.focus();
    const addClaim = () => {
        const id = newId();
        added.current.add(id);
        update(draft => { draft.claims.push({ id, statement: "", reasoning: "", caveats: "", archived: false }); });
    };
    const startFromBrief = () => {
        if (!project) return;
        const imported = legacyCase(project);
        update(draft => {
            draft.case.question = imported.question;
            draft.case.landscape = imported.landscape;
            draft.case.provisional_answer = imported.provisional_answer;
        });
        if (imported.excerpted) toast.message("Copied the first 20,000 characters of the brief. The complete original stays under Discuss.");
    };

    if (isProjectLoading && !project) {
        return <div className="mx-auto w-full max-w-4xl space-y-4 p-6"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-48 w-full" /></div>;
    }

    if (projectError) return <div role="alert" className="p-4 text-destructive">{projectError.message}</div>;
    if (!project) return <div className="p-4">Project not found.</div>;

    const archivedCount = doc.claims.filter(claim => claim.archived).length;
    const shownClaims = doc.claims.map((claim, index) => ({ claim, index })).filter(({ claim }) => showArchived || !claim.archived || claim.id === linkedClaim);
    const hasLegacyBrief = !!(project?.description || project?.research_brief);
    const caseIsEmpty = !Object.entries(doc.case).some(([key, value]) => key !== "search_date" && typeof value === "string" && value.trim());
    const activeFindings = doc.findings.filter(finding => !finding.archived).length;

    return (
        <ViewFrame>
            <fieldset disabled={!loaded} className="min-w-0 space-y-8">
                <header>
                    <p className="text-xs font-medium text-muted-foreground">
                        <span className="[overflow-wrap:anywhere]">{project?.title}</span> · {papers.length} {papers.length === 1 ? "paper" : "papers"} · {activeFindings} {activeFindings === 1 ? "finding" : "findings"} · {doc.claims.length - archivedCount} {doc.claims.length - archivedCount === 1 ? "claim" : "claims"}
                    </p>
                    <div className="mt-2"><FoldedPreview /></div>
                    <h1 className="sr-only">{doc.case.question.trim() || "The case: no question yet"}</h1>
                    <ProseField id="case-question" label="Question" hideLabel size="title" className="mt-2" value={doc.case.question}
                        placeholder="What disputed question should this project resolve?"
                        onChange={value => update(draft => { draft.case.question = value; })} />
                    {!loaded && status !== "Loading" && <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">{status}. Reload the page to try again; nothing can be edited until the investigation loads.</p>}
                    {canEdit && loaded && hasLegacyBrief && caseIsEmpty && (
                        <div className="mt-4 flex flex-wrap items-center gap-3">
                            <Button variant="outline" size="sm" onClick={startFromBrief}>Start from existing brief (unsaved)</Button>
                            <p className="text-xs text-muted-foreground">Copies the question, context and provisional answer from the project brief. Nothing is saved until you save.</p>
                        </div>
                    )}
                </header>

                {canEdit && loaded && <NextStep focusQuestion={focusQuestion} addClaim={addClaim} />}

                <section aria-labelledby="position-heading" className="space-y-4">
                    <SectionHeading id="position-heading" title="Where it stands" description="Your working position. Record uncertainty before drafting an answer." />
                    <div className="grid gap-3 sm:grid-cols-2">
                        {POSITION.map(item => (
                            <div key={item.key} className="rounded-xl bg-muted/40 p-4">
                                <item.icon aria-hidden className="mb-2 h-4 w-4 text-blue-500" />
                                <ProseField label={item.label} placeholder={item.placeholder} value={doc.case[item.key] || ""}
                                    onChange={value => update(draft => { draft.case[item.key] = value; })} />
                            </div>
                        ))}
                    </div>
                </section>

                <section aria-labelledby="claims-heading" className="space-y-2">
                    <SectionHeading id="claims-heading" title="Claims" description="The argument, one claim at a time. Each claim shows the evidence linked to it.">
                        {archivedCount > 0 && <Button variant="ghost" size="sm" aria-pressed={showArchived} onClick={() => setShowArchived(!showArchived)}>{showArchived ? "Hide" : "Show"} archived ({archivedCount})</Button>}
                    </SectionHeading>
                    {shownClaims.length > 0
                        ? <ol className="divide-y">{shownClaims.map(({ claim, index }, position) => <ClaimRow key={claim.id} claim={claim} index={index} before={shownClaims[position - 1]?.index} after={shownClaims[position + 1]?.index} startOpen={added.current.has(claim.id) || claim.id === linkedClaim} />)}</ol>
                        : <p className="py-3 text-sm leading-6 text-muted-foreground">{doc.claims.length ? "Every claim is archived." : "No claims yet. A claim is a statement the evidence can support, challenge or qualify."}</p>}
                    {canEdit && <Button variant="outline" size="sm" onClick={addClaim}><Plus aria-hidden className="h-4 w-4" />Add claim</Button>}
                </section>

                <section aria-labelledby="background-heading" className="space-y-5">
                    <SectionHeading id="background-heading" title="Background" description="Context for the question and the limits of what was searched." />
                    <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
                        {BACKGROUND.map(item => (
                            <ProseField key={item.key} label={item.label} hint={item.hint} placeholder={item.placeholder} value={doc.case[item.key] || ""}
                                onChange={value => update(draft => { draft.case[item.key] = value; })} />
                        ))}
                    </div>
                    <div>
                        <label htmlFor="case-search-date" className="block text-xs font-medium text-muted-foreground">Search date (optional)</label>
                        <p className="mt-0.5 text-xs leading-5 text-muted-foreground/80">When the literature was last searched. Leave empty if no wider search was run.</p>
                        <input id="case-search-date" type="date" disabled={!canEdit} value={doc.case.search_date || ""}
                            onChange={event => update(draft => { draft.case.search_date = event.target.value || null; })}
                            className="mt-1.5 h-8 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-70 dark:bg-input/30" />
                    </div>
                    {canEdit && loaded && hasLegacyBrief && !caseIsEmpty && (
                        <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground" onClick={startFromBrief}>Start from existing brief (unsaved)</Button>
                    )}
                </section>
            </fieldset>
        </ViewFrame>
    );
}

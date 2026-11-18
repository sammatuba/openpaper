"use client";

import { FormEvent, ReactNode, useEffect, useId, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
    Archive,
    ArchiveRestore,
    ChevronDown,
    ExternalLink,
    FileSearch,
    FileText,
    Link2,
    Loader2,
    Plus,
    Quote,
    Search,
    X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Finding, Relation, Source, investigationRequest } from "@/lib/investigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useInvestigation } from "@/components/project/InvestigationProvider";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";
import {
    EmptyState,
    FoldedPreview,
    ProseField,
    RELATIONS,
    RELATION_KINDS,
    RelationTag,
    SourceStatus,
    ViewFrame,
    newId,
    useCanEdit,
} from "./shared";

type AnchoredSource = Extract<Source, { kind: "anchored" }>;
type SetupKey = keyof Finding["setup"];

interface SearchResult {
    paper_id: string;
    start_line: number;
    end_line: number;
    excerpt: string;
    title: string;
}

const SETUP_KEYS: SetupKey[] = ["model", "task", "training", "intervention", "evaluation", "other"];
const MAX_LINE_COUNT = 200;

const STATUS_FILTERS = [
    { value: "current", label: "Source current" },
    { value: "source_changed", label: "Source changed" },
    { value: "unavailable", label: "Source unavailable" },
    { value: "unbound", label: "Awaiting binding" },
];

// Native selects are kept (rather than the shadcn popover select) so they stay
// plain form controls for keyboards, screen readers and browser automation.
const selectClass = cn(
    "h-9 w-full min-w-0 rounded-md border border-input bg-background px-2 text-sm outline-none transition-colors",
    "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
    "disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30",
);
const controlLabelClass = "block text-xs font-medium text-muted-foreground";

function GroupLabel({ children }: { children: ReactNode }) {
    return <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{children}</p>;
}

const claimName = (statement?: string) => statement || "Untitled claim";

export function EvidenceView() {
    const { projectId, papers, isPapersLoading, openAddPapers } = useProjectWorkspace();
    const { document: doc, update, validation, loaded, status } = useInvestigation();
    const canEdit = useCanEdit();
    const params = useSearchParams();
    const ids = useId();

    // Filters. The claim filter starts from `?claim=` until the user picks one.
    const [claimChoice, setClaimChoice] = useState<string | null>(null);
    const [filterRelation, setFilterRelation] = useState("");
    const [filterStatus, setFilterStatus] = useState("");
    const claimParam = params.get("claim");
    const filterClaim = claimChoice ?? (claimParam && doc.claims.some(claim => claim.id === claimParam) ? claimParam : "");

    // Capture panel.
    const [captureToggle, setCaptureToggle] = useState<boolean | null>(null);
    const [paperId, setPaperId] = useState("");
    const [start, setStart] = useState(1);
    const [count, setCount] = useState(1);
    const [inspected, setInspected] = useState<AnchoredSource | null>(null);
    const [inspecting, setInspecting] = useState(false);
    const [error, setError] = useState("");
    const [query, setQuery] = useState("");
    const [searching, setSearching] = useState(false);
    const [searchError, setSearchError] = useState("");
    const [search, setSearch] = useState<{ coverage: string; results: SearchResult[] } | null>(null);
    const inspectRequest = useRef(0);

    // Findings list.
    const [selected, setSelected] = useState<string[]>([]);
    const [opened, setOpened] = useState<Record<string, boolean>>({});
    const [fresh, setFresh] = useState<string[]>([]);
    const lastFocused = useRef("");
    const scrollToNew = useRef("");
    const comparisonRef = useRef<HTMLDivElement>(null);

    const deepLinked = params.get("finding");
    useEffect(() => {
        if (deepLinked && lastFocused.current !== deepLinked && doc.findings.some(finding => finding.id === deepLinked)) {
            window.document.getElementById("finding-" + deepLinked)?.scrollIntoView({ block: "start" });
            lastFocused.current = deepLinked;
        }
    }, [deepLinked, doc.findings]);

    // A newly attached finding lands at the end of the list; bring it into view.
    useEffect(() => {
        if (!scrollToNew.current) return;
        const element = window.document.getElementById("finding-" + scrollToNew.current);
        if (!element) return;
        element.scrollIntoView({ block: "nearest" });
        scrollToNew.current = "";
    }, [doc.findings]);

    const captureOpen = captureToggle ?? (loaded && doc.findings.length === 0);
    const noPapers = !isPapersLoading && papers.length === 0;

    // Any change to the selection invalidates the inspected text, including a
    // response still in flight for the previous selection.
    function resetInspection() {
        inspectRequest.current++;
        setInspected(null);
        setInspecting(false);
    }

    async function inspect(target: { paperId: string; start: number; count: number }) {
        const request = ++inspectRequest.current;
        setError("");
        setInspecting(true);
        try {
            const { body } = await investigationRequest(
                `/api/projects/${projectId}/investigation/sources/${target.paperId}?start_line=${target.start}&line_count=${target.count}`,
            );
            if (request !== inspectRequest.current) return;
            setInspected({
                kind: "anchored",
                paper_id: target.paperId,
                start_line: body.start_line,
                end_line: body.end_line,
                quote: body.text,
                source_sha256: body.source_sha256,
                quote_sha256: body.quote_sha256,
            });
        } catch (failure) {
            if (request !== inspectRequest.current) return;
            setInspected(null);
            setError(failure instanceof Error ? failure.message : String(failure));
        } finally {
            if (request === inspectRequest.current) setInspecting(false);
        }
    }

    async function runSearch(event: FormEvent) {
        event.preventDefault();
        const q = query.trim();
        if (!q) return;
        setSearchError("");
        setSearching(true);
        try {
            const { body } = await investigationRequest(
                `/api/projects/${projectId}/investigation/sources/search?q=${encodeURIComponent(q)}&limit=10`,
            );
            setSearch({ coverage: body.coverage || "", results: Array.isArray(body.results) ? body.results : [] });
        } catch (failure) {
            setSearch(null);
            setSearchError(failure instanceof Error ? failure.message : String(failure));
        } finally {
            setSearching(false);
        }
    }

    // The excerpt only locates the lines; the anchored text always comes from
    // the source endpoint so its digests match what the server will verify.
    function inspectResult(result: SearchResult) {
        const target = {
            paperId: result.paper_id,
            start: result.start_line,
            count: Math.min(Math.max(result.end_line - result.start_line + 1, 1), MAX_LINE_COUNT),
        };
        setPaperId(target.paperId);
        setStart(target.start);
        setCount(target.count);
        setInspected(null);
        void inspect(target);
    }

    function attach() {
        if (!inspected) return;
        const id = newId();
        const source = inspected;
        update(d => {
            d.findings.push({
                id,
                label: "New finding",
                observed_result: "",
                author_interpretation: "",
                our_interpretation: "",
                setup: { model: "", task: "", training: "", intervention: "", evaluation: "", other: "" },
                limitations: "",
                source,
                archived: false,
            });
        });
        setInspected(null);
        setOpened(previous => ({ ...previous, [id]: true }));
        setFresh(previous => [...previous, id]);
        setCaptureToggle(true);
        // A new finding has no relations or saved status, so any filter would hide it.
        setClaimChoice("");
        setFilterRelation("");
        setFilterStatus("");
        scrollToNew.current = id;
    }

    function clearFilters() {
        setClaimChoice("");
        setFilterRelation("");
        setFilterStatus("");
    }

    const visible = doc.findings
        .filter(finding => !filterStatus || validation.findings[finding.id] === filterStatus)
        .filter(
            finding =>
                (!filterClaim && !filterRelation) ||
                doc.relations.some(
                    relation =>
                        relation.finding_id === finding.id &&
                        (!filterClaim || relation.claim_id === filterClaim) &&
                        (!filterRelation || relation.relation === filterRelation),
                ),
        );
    const filtering = Boolean(filterClaim || filterRelation || filterStatus);
    const selectedFindings = doc.findings.filter(finding => selected.includes(finding.id));

    const archivedCount = doc.findings.filter(finding => finding.archived).length;
    const relatedCount = new Set(doc.relations.map(relation => relation.finding_id)).size;
    const paperTitle = (source: AnchoredSource) =>
        source.title || papers.find(paper => paper.id === source.paper_id)?.title || "Project source";

    const comparisonRows: { label: string; value: (finding: Finding) => string }[] = [
        { label: "Observed result", value: finding => finding.observed_result },
        { label: "Author interpretation", value: finding => finding.author_interpretation },
        { label: "Our interpretation", value: finding => finding.our_interpretation },
        ...SETUP_KEYS.map(key => ({ label: `Setup · ${key}`, value: (finding: Finding) => finding.setup[key] })),
        { label: "Limitations", value: finding => finding.limitations },
    ];

    return (
        <ViewFrame wide>
            <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
                <div className="min-w-0 max-w-2xl space-y-2">
                    <h1 className="text-2xl font-bold tracking-tight">Evidence</h1>
                    <p className="text-sm leading-6 text-muted-foreground">
                        Findings anchored to exact extracted lines of the project&apos;s sources. What a source reports is kept apart
                        from what anyone concludes from it.
                    </p>
                    {loaded && doc.findings.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                            {doc.findings.length} {doc.findings.length === 1 ? "finding" : "findings"} · {relatedCount} related to a claim
                            {archivedCount > 0 && ` · ${archivedCount} archived`}
                        </p>
                    )}
                </div>
                {!noPapers && (
                    <Button
                        variant={captureOpen ? "outline" : "default"}
                        aria-expanded={captureOpen}
                        disabled={!loaded}
                        onClick={() => setCaptureToggle(!captureOpen)}
                    >
                        {canEdit ? <Plus aria-hidden className="h-4 w-4" /> : <FileSearch aria-hidden className="h-4 w-4" />}
                        {canEdit ? "Add finding" : "Inspect source text"}
                    </Button>
                )}
            </header>

            {!loaded && (
                <p className="text-sm text-muted-foreground">
                    {status === "Loading" ? "Loading the investigation…" : "The investigation has not loaded, so it cannot be edited yet."}
                </p>
            )}

            <fieldset disabled={!loaded} className="min-w-0 space-y-8">
                {loaded && noPapers && (
                    <EmptyState icon={FileText} title="Add a source first">
                        <p>Findings are captured from the extracted text of papers in this project. There are no papers here yet.</p>
                        {canEdit && (
                            <Button variant="outline" size="sm" onClick={() => openAddPapers()}>
                                <Plus aria-hidden className="h-4 w-4" />
                                Add papers
                            </Button>
                        )}
                    </EmptyState>
                )}

                {captureOpen && !noPapers && (
                    <div className="min-w-0 space-y-6 rounded-xl border p-4 sm:p-5">
                        <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                                <h2 className="text-lg font-semibold">Capture from a source</h2>
                                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                    Select exact extracted-text lines. PDF page mapping is unknown unless verified.
                                </p>
                            </div>
                            <Button variant="ghost" size="icon" aria-label="Close capture panel" onClick={() => setCaptureToggle(false)}>
                                <X aria-hidden className="h-4 w-4" />
                            </Button>
                        </div>

                        <div className="space-y-3">
                            <form onSubmit={runSearch} className="space-y-1.5">
                                <label htmlFor={ids + "query"} className={controlLabelClass}>
                                    Search the project&apos;s sources
                                </label>
                                <div className="flex gap-2">
                                    <Input
                                        id={ids + "query"}
                                        type="search"
                                        maxLength={200}
                                        value={query}
                                        placeholder="A phrase, method or result"
                                        onChange={event => setQuery(event.target.value)}
                                        className="min-w-0 flex-1"
                                    />
                                    <Button type="submit" variant="outline" disabled={!query.trim() || searching}>
                                        {searching ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Search aria-hidden className="h-4 w-4" />}
                                        Search
                                    </Button>
                                </div>
                            </form>
                            {searchError && (
                                <p role="alert" className="text-sm text-red-700 dark:text-red-400">
                                    {searchError}
                                </p>
                            )}
                            {search && (
                                <div className="space-y-2">
                                    {search.results.length === 0 ? (
                                        <p className="text-sm text-muted-foreground">No indexed passage matches that search.</p>
                                    ) : (
                                        <ul className="divide-y">
                                            {search.results.map(result => (
                                                <li
                                                    key={`${result.paper_id}:${result.start_line}:${result.end_line}`}
                                                    className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 py-3"
                                                >
                                                    <div className="min-w-0 flex-1 basis-64 space-y-1">
                                                        <p className="text-sm font-medium [overflow-wrap:anywhere]">
                                                            {result.title || "Untitled paper"}
                                                            <span className="ml-2 text-xs font-normal text-muted-foreground">
                                                                lines {result.start_line}–{result.end_line}
                                                            </span>
                                                        </p>
                                                        <p className="line-clamp-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
                                                            {result.excerpt}
                                                        </p>
                                                    </div>
                                                    <Button type="button" variant="outline" size="sm" onClick={() => inspectResult(result)}>
                                                        Use these lines
                                                    </Button>
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                    {search.coverage && <p className="text-xs text-muted-foreground">{search.coverage}</p>}
                                </div>
                            )}
                        </div>

                        <div className="space-y-2">
                            <GroupLabel>Choose lines directly</GroupLabel>
                            <div className="grid items-end gap-3 sm:grid-cols-[minmax(0,1fr)_7rem_7rem_auto]">
                                <div className="min-w-0 space-y-1.5">
                                    <label htmlFor={ids + "paper"} className={controlLabelClass}>
                                        Project source
                                    </label>
                                    <select
                                        id={ids + "paper"}
                                        className={selectClass}
                                        value={paperId}
                                        onChange={event => {
                                            setPaperId(event.target.value);
                                            resetInspection();
                                        }}
                                    >
                                        <option value="">Choose paper</option>
                                        {papers.map(paper => (
                                            <option key={paper.id} value={paper.id}>
                                                {paper.title}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div className="space-y-1.5">
                                    <label htmlFor={ids + "start"} className={controlLabelClass}>
                                        Start line
                                    </label>
                                    <Input
                                        id={ids + "start"}
                                        type="number"
                                        min={1}
                                        value={start}
                                        onChange={event => {
                                            setStart(Number(event.target.value));
                                            resetInspection();
                                        }}
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <label htmlFor={ids + "count"} className={controlLabelClass}>
                                        Line count
                                    </label>
                                    <Input
                                        id={ids + "count"}
                                        type="number"
                                        min={1}
                                        max={MAX_LINE_COUNT}
                                        value={count}
                                        onChange={event => {
                                            setCount(Number(event.target.value));
                                            resetInspection();
                                        }}
                                    />
                                </div>
                                <Button type="button" variant="outline" disabled={!paperId || inspecting} onClick={() => void inspect({ paperId, start, count })}>
                                    {inspecting && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                                    Inspect source lines
                                </Button>
                            </div>
                            {error && (
                                <p role="alert" className="text-sm text-red-700 dark:text-red-400">
                                    {error}
                                </p>
                            )}
                        </div>

                        {inspected && (
                            <div className="space-y-3 rounded-md bg-muted/40 p-3 sm:p-4">
                                <p className="flex items-center gap-1.5 text-xs font-medium [overflow-wrap:anywhere]">
                                    <Quote aria-hidden className="h-3.5 w-3.5 shrink-0 text-blue-600 dark:text-blue-400" />
                                    {paperTitle(inspected)}
                                </p>
                                <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 [overflow-wrap:anywhere]">{inspected.quote}</pre>
                                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                                    <p className="text-xs text-muted-foreground">
                                        Extracted lines {inspected.start_line}–{inspected.end_line}; PDF page not mapped.
                                    </p>
                                    <Button type="button" disabled={!canEdit} onClick={attach}>
                                        Attach as finding
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {loaded && !noPapers && doc.findings.length === 0 && (
                    <EmptyState icon={Quote} title="No findings yet">
                        <p>
                            A finding is one reported result, pinned to the exact lines it comes from. Record what the source observed first;
                            the authors&apos; reading and your own are kept in separate fields so they can be compared later.
                        </p>
                    </EmptyState>
                )}

                {doc.findings.length > 0 && (
                    <div className="min-w-0 space-y-4">
                        <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
                            <h2 className="text-lg font-semibold">Findings</h2>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                                {filtering && (
                                    <span>
                                        Showing {visible.length} of {doc.findings.length}
                                    </span>
                                )}
                                {filtering && (
                                    <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
                                        Clear filters
                                    </Button>
                                )}
                                {selectedFindings.length > 0 && (
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => comparisonRef.current?.scrollIntoView({ block: "start" })}
                                    >
                                        Compare {selectedFindings.length} selected
                                    </Button>
                                )}
                            </div>
                        </div>

                        <div className="grid gap-3 sm:grid-cols-3">
                            <div className="min-w-0 space-y-1.5">
                                <label htmlFor={ids + "f-claim"} className={controlLabelClass}>
                                    Filter by claim
                                </label>
                                <select id={ids + "f-claim"} className={selectClass} value={filterClaim} onChange={event => setClaimChoice(event.target.value)}>
                                    <option value="">All claims</option>
                                    {doc.claims.map(claim => (
                                        <option key={claim.id} value={claim.id}>
                                            {claimName(claim.statement)}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="min-w-0 space-y-1.5">
                                <label htmlFor={ids + "f-relation"} className={controlLabelClass}>
                                    Filter by relationship
                                </label>
                                <select
                                    id={ids + "f-relation"}
                                    className={selectClass}
                                    value={filterRelation}
                                    onChange={event => setFilterRelation(event.target.value)}
                                >
                                    <option value="">All relationships</option>
                                    {RELATION_KINDS.map(kind => (
                                        <option key={kind} value={kind}>
                                            {RELATIONS[kind].label}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="min-w-0 space-y-1.5">
                                <label htmlFor={ids + "f-status"} className={controlLabelClass}>
                                    Filter by source status
                                </label>
                                <select id={ids + "f-status"} className={selectClass} value={filterStatus} onChange={event => setFilterStatus(event.target.value)}>
                                    <option value="">All source statuses</option>
                                    {STATUS_FILTERS.map(option => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        {visible.length === 0 && <p className="py-4 text-sm text-muted-foreground">No findings match these filters.</p>}

                        <div className="min-w-0 space-y-4">
                            {visible.map(finding => (
                                <FindingCard
                                    key={finding.id}
                                    finding={finding}
                                    expanded={opened[finding.id] ?? finding.id === deepLinked}
                                    fresh={fresh.includes(finding.id)}
                                    selected={selected.includes(finding.id)}
                                    inspected={inspected}
                                    onToggle={next => setOpened(previous => ({ ...previous, [finding.id]: next }))}
                                    onSelect={checked =>
                                        setSelected(previous => (checked ? [...previous, finding.id] : previous.filter(id => id !== finding.id)))
                                    }
                                    onRebound={() => setInspected(null)}
                                />
                            ))}
                        </div>
                    </div>
                )}

                {selectedFindings.length > 0 && (
                    <div ref={comparisonRef} className="min-w-0 space-y-4 rounded-xl bg-muted/40 p-4 sm:p-5">
                        <h2 className="text-lg font-semibold">Selected comparison</h2>
                        <p className="text-sm leading-6 text-muted-foreground">
                            Read across the rows: where the observed results agree but the interpretations differ, the setup rows usually say why.
                        </p>
                        <div className="overflow-x-auto rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50" tabIndex={0} role="group" aria-label="Side-by-side table">
                            <table className="w-full border-collapse text-left text-sm" style={{ minWidth: `${9 + selectedFindings.length * 15}rem` }}>
                                <thead>
                                    <tr className="border-b">
                                        <th scope="row" className="w-36 py-2.5 pr-4 align-top text-xs font-medium text-muted-foreground">
                                            Label
                                        </th>
                                        {selectedFindings.map(finding => (
                                            <th key={finding.id} scope="col" className="py-2.5 pr-4 align-top font-semibold [overflow-wrap:anywhere]">
                                                {finding.label || "Not recorded"}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {comparisonRows.map(row => (
                                        <tr key={row.label}>
                                            <th scope="row" className="w-36 py-2.5 pr-4 align-top text-xs font-medium text-muted-foreground">
                                                {row.label}
                                            </th>
                                            {selectedFindings.map(finding => {
                                                const value = row.value(finding);
                                                return (
                                                    <td
                                                        key={finding.id}
                                                        className={cn(
                                                            "whitespace-pre-wrap py-2.5 pr-4 align-top leading-6 [overflow-wrap:anywhere]",
                                                            !value && "text-muted-foreground",
                                                        )}
                                                    >
                                                        {value || "Not recorded"}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    ))}
                                    <tr>
                                        <th scope="row" className="w-36 py-2.5 pr-4 align-top text-xs font-medium text-muted-foreground">
                                            Source
                                        </th>
                                        {selectedFindings.map(finding => (
                                            <td key={finding.id} className="py-2.5 pr-4 align-top leading-6 [overflow-wrap:anywhere]">
                                                {finding.source.kind === "anchored" ? (
                                                    <p>
                                                        {paperTitle(finding.source)} · extracted lines {finding.source.start_line}–{finding.source.end_line}
                                                    </p>
                                                ) : (
                                                    <p className="text-muted-foreground">Source unavailable or unbound</p>
                                                )}
                                            </td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <th scope="row" className="w-36 py-2.5 pr-4 align-top text-xs font-medium text-muted-foreground">
                                            Quote
                                        </th>
                                        {selectedFindings.map(finding => (
                                            <td key={finding.id} className="py-2.5 pr-4 align-top leading-6">
                                                {finding.source.kind === "anchored" ? (
                                                    <blockquote className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{finding.source.quote}</blockquote>
                                                ) : (
                                                    <span className="text-muted-foreground">Not recorded</span>
                                                )}
                                            </td>
                                        ))}
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        <ProseField
                            label="Candidate reconciliation (our interpretation)"
                            value={doc.case.reconciliation}
                            placeholder="How could these findings both be true?"
                            onChange={value =>
                                update(d => {
                                    d.case.reconciliation = value;
                                })
                            }
                        />
                    </div>
                )}
            </fieldset>

            <FoldedPreview view="evidence" />
        </ViewFrame>
    );
}

interface FindingCardProps {
    finding: Finding;
    expanded: boolean;
    // Attached during this session: starts fully open, setup included.
    fresh: boolean;
    selected: boolean;
    inspected: AnchoredSource | null;
    onToggle: (expanded: boolean) => void;
    onSelect: (selected: boolean) => void;
    onRebound: () => void;
}

function FindingCard({ finding, expanded, fresh, selected, inspected, onToggle, onSelect, onRebound }: FindingCardProps) {
    const { document: doc, update, validation } = useInvestigation();
    const { papers, openPaper } = useProjectWorkspace();
    const canEdit = useCanEdit();
    const ids = useId();
    // Decided once, so the grid does not fold away while its last field is being cleared.
    const [setupOpen, setSetupOpen] = useState(() => fresh || SETUP_KEYS.some(key => finding.setup[key]));

    const source = finding.source;
    const paper = source.kind === "anchored" ? papers.find(item => item.id === source.paper_id) : undefined;
    const relations = doc.relations.filter(relation => relation.finding_id === finding.id);
    const claimStatement = (relation: Relation) => claimName(doc.claims.find(claim => claim.id === relation.claim_id)?.statement);

    const edit = (change: (target: Finding) => void) =>
        update(d => {
            const target = d.findings.find(item => item.id === finding.id);
            if (target) change(target);
        });
    const editRelation = (id: string, change: (target: Relation) => void) =>
        update(d => {
            const target = d.relations.find(item => item.id === id);
            if (target) change(target);
        });

    function relate(claimId: string) {
        if (!claimId) return;
        update(d => {
            const exists = d.relations.some(
                relation => relation.claim_id === claimId && relation.finding_id === finding.id && relation.relation === "supports",
            );
            if (!exists) d.relations.push({ id: newId(), claim_id: claimId, finding_id: finding.id, relation: "supports", rationale: "" });
        });
    }

    return (
        <article id={"finding-" + finding.id} className="min-w-0 scroll-mt-4 rounded-xl border p-4 sm:p-5">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    {expanded ? (
                        <ProseField
                            label="Label"
                            value={finding.label}
                            maxLength={500}
                            placeholder="A short name for this finding"
                            inputClassName="text-base font-semibold leading-6"
                            onChange={value => edit(target => { target.label = value; })}
                        />
                    ) : (
                        <h3 className="text-base font-semibold leading-6 [overflow-wrap:anywhere]">{finding.label || "Untitled finding"}</h3>
                    )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                    {finding.archived && <Badge variant="secondary">Archived</Badge>}
                    <Button type="button" variant="ghost" size="sm" aria-expanded={expanded} onClick={() => onToggle(!expanded)}>
                        {expanded ? "Collapse" : canEdit ? "Edit details" : "Show details"}
                        <ChevronDown aria-hidden className={cn("h-4 w-4 transition-transform duration-200", expanded && "rotate-180")} />
                    </Button>
                </div>
            </div>

            <div className={cn("mt-4 grid gap-x-10 gap-y-6", expanded && "lg:grid-cols-2")}>
                <div className="min-w-0 space-y-4">
                    {expanded && <GroupLabel>What the source reports</GroupLabel>}
                    {source.kind === "anchored" ? (
                        <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                                <span className="inline-flex min-w-0 items-center gap-1.5 text-xs font-medium">
                                    <FileText aria-hidden className="h-3.5 w-3.5 shrink-0 text-blue-600 dark:text-blue-400" />
                                    <span className="[overflow-wrap:anywhere]">{source.title || paper?.title || "Project source"}</span>
                                </span>
                                <span className="text-xs text-muted-foreground">
                                    Extracted lines {source.start_line}–{source.end_line}
                                </span>
                                <SourceStatus status={validation.findings[finding.id]} />
                            </div>
                            <blockquote
                                className={cn(
                                    "whitespace-pre-wrap break-words rounded-md bg-muted/40 px-3 py-2.5 text-sm leading-6 [overflow-wrap:anywhere]",
                                    !expanded && "line-clamp-4",
                                )}
                            >
                                {source.quote}
                            </blockquote>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                                <Button type="button" variant="outline" size="sm" disabled={!paper} onClick={() => paper && openPaper(paper, source.quote)}>
                                    <ExternalLink aria-hidden className="h-4 w-4" />
                                    Open PDF source
                                </Button>
                                <p className="min-w-0 flex-1 basis-56 text-xs text-muted-foreground">
                                    Exact extracted quote shown above. PDF text search may fail; page is not mapped.
                                </p>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-1">
                            <SourceStatus status={validation.findings[finding.id]} />
                            <p className="text-sm text-muted-foreground">Source unavailable or awaiting binding.</p>
                        </div>
                    )}

                    {expanded ? (
                        <ProseField
                            label="Observed result"
                            value={finding.observed_result}
                            placeholder="What was measured or shown, in the source's own terms"
                            onChange={value => edit(target => { target.observed_result = value; })}
                        />
                    ) : (
                        <p className={cn("line-clamp-2 text-sm leading-6 [overflow-wrap:anywhere]", !finding.observed_result && "text-muted-foreground")}>
                            {finding.observed_result || "Observed result not recorded yet."}
                        </p>
                    )}
                </div>

                {expanded && (
                    <div className="min-w-0 space-y-4">
                        <GroupLabel>Interpretation</GroupLabel>
                        <ProseField
                            label="Author interpretation"
                            value={finding.author_interpretation}
                            placeholder="What the authors conclude from the result"
                            onChange={value => edit(target => { target.author_interpretation = value; })}
                        />
                        <ProseField
                            label="Our interpretation"
                            value={finding.our_interpretation}
                            placeholder="What we take it to show, and where we differ"
                            onChange={value => edit(target => { target.our_interpretation = value; })}
                        />
                        <ProseField
                            label="Limitations"
                            value={finding.limitations}
                            placeholder="What this result cannot tell us"
                            onChange={value => edit(target => { target.limitations = value; })}
                        />
                    </div>
                )}
            </div>

            {expanded && (
                <div className="mt-6 space-y-6">
                    <div className="space-y-3">
                        <button
                            type="button"
                            aria-expanded={setupOpen}
                            onClick={() => setSetupOpen(!setupOpen)}
                            className="-mx-1 inline-flex items-center gap-1.5 rounded-md px-1 py-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
                        >
                            <ChevronDown aria-hidden className={cn("h-3.5 w-3.5 transition-transform duration-200", !setupOpen && "-rotate-90")} />
                            Experimental setup
                            {!setupOpen && <span className="font-normal normal-case tracking-normal">· not recorded</span>}
                        </button>
                        {setupOpen && (
                            <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                                {SETUP_KEYS.map(key => (
                                    <ProseField
                                        key={key}
                                        label={"Setup: " + key}
                                        value={finding.setup[key]}
                                        onChange={value => edit(target => { target.setup[key] = value; })}
                                    />
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="space-y-3">
                        <GroupLabel>Bearing on claims</GroupLabel>
                        {relations.length === 0 && <p className="text-sm text-muted-foreground">Not yet related to a claim.</p>}
                        {relations.length > 0 && (
                            <ul className="space-y-4">
                                {relations.map(relation => (
                                    <li key={relation.id} className="space-y-1.5">
                                        <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
                                            <RelationTag relation={relation.relation} className="mt-0.5" />
                                            <p className="min-w-0 flex-1 basis-56 text-sm leading-6 [overflow-wrap:anywhere]">{claimStatement(relation)}</p>
                                            {canEdit && (
                                                <div className="flex items-center gap-1">
                                                    <select
                                                        aria-label="Relationship type"
                                                        className={cn(selectClass, "h-8 w-auto")}
                                                        value={relation.relation}
                                                        onChange={event =>
                                                            editRelation(relation.id, target => {
                                                                target.relation = event.target.value as Relation["relation"];
                                                            })
                                                        }
                                                    >
                                                        {RELATION_KINDS.map(kind => (
                                                            // A second relation of the same kind to the same claim would not save.
                                                            <option
                                                                key={kind}
                                                                value={kind}
                                                                disabled={relations.some(
                                                                    other => other.id !== relation.id && other.claim_id === relation.claim_id && other.relation === kind,
                                                                )}
                                                            >
                                                                {RELATIONS[kind].label}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    <Button
                                                        type="button"
                                                        variant="ghost"
                                                        size="icon"
                                                        className="size-8"
                                                        aria-label="Remove relation"
                                                        onClick={() =>
                                                            update(d => {
                                                                d.relations = d.relations.filter(item => item.id !== relation.id);
                                                            })
                                                        }
                                                    >
                                                        <X aria-hidden className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            )}
                                        </div>
                                        <ProseField
                                            label="Relationship rationale"
                                            value={relation.rationale}
                                            placeholder="Why this finding bears on the claim this way"
                                            onChange={value => editRelation(relation.id, target => { target.rationale = value; })}
                                        />
                                    </li>
                                ))}
                            </ul>
                        )}
                        {canEdit && (
                            <div className="max-w-md space-y-1.5">
                                <label htmlFor={ids + "relate"} className={controlLabelClass}>
                                    Relate to claim
                                </label>
                                {/* Stays on the empty option: choosing a claim is an action, not a stored value. */}
                                <select id={ids + "relate"} className={selectClass} value="" onChange={event => relate(event.target.value)}>
                                    <option value="">Choose claim</option>
                                    {doc.claims.map(claim => (
                                        <option key={claim.id} value={claim.id}>
                                            {claimName(claim.statement)}
                                        </option>
                                    ))}
                                </select>
                                {doc.claims.length === 0 && <p className="text-xs text-muted-foreground">No claims have been recorded for this project yet.</p>}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {!expanded && relations.length > 0 && (
                <ul className="mt-4 flex flex-wrap gap-2">
                    {relations.map(relation => (
                        <li key={relation.id} className="inline-flex min-w-0 max-w-full items-center gap-2 rounded-full bg-muted px-2.5 py-1">
                            <RelationTag relation={relation.relation} className="shrink-0" />
                            <span className="truncate text-xs text-muted-foreground">{claimStatement(relation)}</span>
                        </li>
                    ))}
                </ul>
            )}

            <div className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <label htmlFor={ids + "compare"} className="inline-flex items-center gap-2 text-sm">
                    <input
                        id={ids + "compare"}
                        type="checkbox"
                        checked={selected}
                        onChange={event => onSelect(event.target.checked)}
                        className="h-4 w-4 rounded accent-blue-600 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:accent-blue-400"
                    />
                    Select for comparison
                </label>
                {canEdit && (
                    <div className="flex flex-wrap items-center gap-1">
                        {inspected && (
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                    edit(target => { target.source = inspected; });
                                    onRebound();
                                }}
                            >
                                <Link2 aria-hidden className="h-4 w-4" />
                                Rebind to inspected quotation
                            </Button>
                        )}
                        <Button type="button" variant="ghost" size="sm" onClick={() => edit(target => { target.archived = !finding.archived; })}>
                            {finding.archived ? <ArchiveRestore aria-hidden className="h-4 w-4" /> : <Archive aria-hidden className="h-4 w-4" />}
                            {finding.archived ? "Restore finding" : "Archive finding"}
                        </Button>
                    </div>
                )}
            </div>
        </article>
    );
}

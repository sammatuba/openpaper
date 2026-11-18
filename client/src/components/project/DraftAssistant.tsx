"use client";

import { useEffect, useId, useRef, useState } from "react";
import { FileSearch, Loader2, Sparkles } from "lucide-react";
import { investigationRequest } from "@/lib/investigation";
import { fetchFromApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useProjectWorkspace } from "./ProjectWorkspaceProvider";
import { useInvestigation } from "./InvestigationProvider";

type Proposal = {
    text: string;
    finding_ids: string[];
    claim_ids: string[];
    request_id: string;
    message_id: string;
    section_id: string;
    stale: boolean;
    uncited: boolean;
};

const labelClass = "block text-xs font-medium text-muted-foreground";
const controlClass =
    "mt-1 block w-full min-w-0 rounded-md border border-input bg-background px-2 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40";

export function DraftAssistant({ sectionId, findingIds, claimIds }: { sectionId: string; findingIds: string[]; claimIds: string[] }) {
    const { projectId, papers, openPaper } = useProjectWorkspace();
    const { document, dirty, revision, update, reviewProposal } = useInvestigation();
    const [open, setOpen] = useState(false);
    const [models, setModels] = useState<string[]>([]);
    const [provider, setProvider] = useState("");
    const [instructions, setInstructions] = useState("");
    const [inspected, setInspected] = useState<string | null>(null);
    const [state, setState] = useState("");
    const [id, setId] = useState<string | null>(null);
    const [proposal, setProposal] = useState<Proposal | null>(null);
    const [reviewed, setReviewed] = useState(false);
    const abort = useRef<AbortController | null>(null);
    const generating = useRef(false);
    const fieldId = useId();

    useEffect(() => () => abort.current?.abort(), []);

    const url = `/api/projects/${projectId}/investigation/draft-requests`;
    const finding = document.findings.find(f => f.id === inspected);
    const omitted = document.findings.filter(
        f => !findingIds.includes(f.id) && (!claimIds.length || document.relations.some(r => r.finding_id === f.id && claimIds.includes(r.claim_id))),
    );

    // Opening the panel only lists the configured models; it sends no research
    // content and makes no provider call.
    async function show() {
        setOpen(true);
        try {
            const options = await fetchFromApi("/api/message/models");
            const names = Object.keys(options.models || {});
            setModels(names);
            setProvider(names.includes(options.default) ? options.default : names[0] || "");
        } catch {
            setState("Model options unavailable. Manual drafting remains available.");
        }
    }

    async function check(requestId = id) {
        if (!requestId) return;
        try {
            const { body } = await investigationRequest(url + "/" + requestId);
            setState(body.error_code || body.state);
            if (body.proposal) setProposal(body.proposal);
        } catch {
            setState("Could not read status. Your input is preserved; try Check status.");
        }
    }

    async function generate() {
        if (generating.current) return;
        generating.current = true;
        setState("Generating");
        setProposal(null);
        setReviewed(false);
        const requestId = crypto.randomUUID();
        setId(requestId);
        abort.current = new AbortController();
        try {
            await investigationRequest(url, {
                method: "POST",
                signal: abort.current.signal,
                body: JSON.stringify({
                    id: requestId,
                    base_revision: revision,
                    section_id: sectionId,
                    claim_ids: claimIds,
                    finding_ids: findingIds,
                    instructions,
                    provider,
                }),
            });
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${url}/${requestId}/run`, {
                method: "POST",
                credentials: "include",
                signal: abort.current.signal,
            });
            if (!response.ok || !response.body) throw Error("Generation did not start.");
            const reader = response.body.getReader();
            try {
                while (!(await reader.read()).done) {
                    /* Results are only accepted from the authorized status endpoint. */
                }
            } finally {
                reader.releaseLock();
            }
            await check(requestId);
        } catch {
            setState("Generation response interrupted. Check status before starting a new request.");
        } finally {
            generating.current = false;
            abort.current = null;
        }
    }

    function insert() {
        if (!proposal || ((proposal.stale || dirty) && !reviewed)) return;
        const section = document.manuscript.sections.find(s => s.id === proposal.section_id);
        if (!section) {
            setState("Target section changed; proposal preserved.");
            return;
        }
        if (proposal.stale || dirty) reviewProposal(proposal.request_id);
        update(d => {
            d.manuscript.sections.find(s => s.id === proposal.section_id)!.blocks.push({
                id: crypto.randomUUID(),
                kind: "paragraph",
                text: proposal.text,
                claim_ids: proposal.claim_ids,
                finding_ids: proposal.finding_ids,
                provenance: { kind: "assistant", request_id: proposal.request_id, message_id: proposal.message_id },
                dependency_pins: {},
            });
        });
        setProposal(null);
        setState("Inserted into unsaved draft. Save investigation to persist.");
    }

    return (
        <div className="space-y-4">
            <Button type="button" variant="outline" size="sm" aria-expanded={open} onClick={() => void show()}>
                <Sparkles aria-hidden className="h-4 w-4" />
                Draft with assistant
            </Button>

            {open && (
                <div className="space-y-4">
                    <p className="text-sm leading-6">
                        Only the {findingIds.length} selected findings will be sent. Other project evidence is omitted. Review your selection before generating. Manual drafting uses no model credits.
                    </p>

                    <details className="text-sm">
                        <summary className="w-fit cursor-pointer rounded-sm font-medium text-blue-600 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:text-blue-400">
                            Review selected context and omissions
                        </summary>
                        <div className="mt-3 space-y-4 leading-6">
                            <div className="text-muted-foreground">
                                <p>Target section: {document.manuscript.sections.find(s => s.id === sectionId)?.title}</p>
                                <p>
                                    Saved case fields accompany these claims: {claimIds.map(claimId => document.claims.find(c => c.id === claimId)?.statement).join("; ") || "None selected"}.
                                </p>
                            </div>
                            {findingIds.map(findingId => {
                                const item = document.findings.find(f => f.id === findingId);
                                return item && (
                                    <article key={findingId} className="min-w-0 space-y-1">
                                        <h3 className="font-medium">{item.label}</h3>
                                        <p>Observed: {item.observed_result}</p>
                                        <p>Setup: {Object.values(item.setup).filter(Boolean).join("; ") || "Not recorded"}</p>
                                        <p>Limitations: {item.limitations || "Not recorded"}</p>
                                        <blockquote className="whitespace-pre-wrap break-words border-l-2 border-blue-500 pl-3 text-muted-foreground dark:border-blue-400">
                                            {item.source.kind === "anchored" ? item.source.quote : "Source unavailable or unbound"}
                                        </blockquote>
                                    </article>
                                );
                            })}
                            <div>
                                <p className="font-medium">Omitted findings for this selection:</p>
                                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted-foreground">
                                    {omitted.map(item => (
                                        <li key={item.id} className="[overflow-wrap:anywhere]">
                                            {item.label} · {document.relations.filter(r => r.finding_id === item.id && (!claimIds.length || claimIds.includes(r.claim_id))).map(r => r.relation).join(", ") || "No selected claim relation"}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                            <p className="text-muted-foreground">Revise the claim/evidence selection above before Generate. No omitted evidence is sent.</p>
                        </div>
                    </details>

                    <div className="grid min-w-0 gap-4 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
                        <div className="min-w-0">
                            <label htmlFor={fieldId + "-provider"} className={labelClass}>Configured provider</label>
                            <select id={fieldId + "-provider"} className={controlClass} value={provider} onChange={event => setProvider(event.target.value)}>
                                {models.map(model => <option key={model}>{model}</option>)}
                            </select>
                        </div>
                        <div className="min-w-0">
                            <label htmlFor={fieldId + "-instructions"} className={labelClass}>Drafting instructions</label>
                            <textarea
                                id={fieldId + "-instructions"}
                                className={controlClass + " min-h-16 leading-6"}
                                maxLength={2000}
                                value={instructions}
                                onChange={event => setInstructions(event.target.value)}
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <div className="flex flex-wrap gap-2">
                            <Button type="button" size="sm" disabled={dirty || !provider || !findingIds.length || state === "Generating"} onClick={() => void generate()}>
                                {state === "Generating" ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                                Generate paragraph
                            </Button>
                            <Button type="button" variant="outline" size="sm" disabled={!id} onClick={() => void check()}>Check request status</Button>
                            <Button type="button" variant="ghost" size="sm" disabled={state !== "Generating"} onClick={() => abort.current?.abort()}>Cancel generation</Button>
                        </div>
                        {dirty && <p className="text-xs leading-5 text-muted-foreground">Save current edits before generating.</p>}
                        <p role="status" className="text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">{state}</p>
                    </div>

                    {proposal && (
                        <div className="space-y-3 rounded-md bg-blue-50 p-3 dark:bg-blue-950/40">
                            <p className="flex items-start gap-1.5 text-xs font-medium leading-5">
                                <Sparkles aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-600 dark:text-blue-400" />
                                <span>AI-authored proposal · {proposal.uncited ? "Uncited prose" : "Citations validated against selected findings; review factual accuracy."}</span>
                            </p>
                            <textarea
                                aria-label="Assistant proposal"
                                className={controlClass + " mt-0 min-h-32 text-base leading-7 field-sizing-content"}
                                value={proposal.text}
                                onChange={event => setProposal({ ...proposal, text: event.target.value })}
                            />
                            {proposal.finding_ids.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                    {proposal.finding_ids.map(fid => (
                                        <Button type="button" variant="outline" size="sm" className="h-auto min-h-8 max-w-full whitespace-normal py-1 text-left" key={fid} onClick={() => setInspected(fid)}>
                                            <FileSearch aria-hidden className="h-4 w-4" />
                                            Inspect {document.findings.find(f => f.id === fid)?.label || "Unavailable finding"}
                                        </Button>
                                    ))}
                                </div>
                            )}
                            {(proposal.stale || dirty) && (
                                <label className="flex items-start gap-2 text-sm leading-5">
                                    <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600 dark:accent-blue-400" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />
                                    <span>I reviewed this proposal against the current workspace and evidence.</span>
                                </label>
                            )}
                            <div className="flex flex-wrap gap-2">
                                <Button type="button" size="sm" disabled={(proposal.stale || dirty) && !reviewed} onClick={insert}>Insert assistant paragraph</Button>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                        setProposal(null);
                                        setState("Proposal discarded. Manuscript unchanged.");
                                    }}
                                >
                                    Discard proposal
                                </Button>
                            </div>
                        </div>
                    )}

                    {finding && (
                        <aside aria-label="Proposal source context" className="min-w-0 space-y-2 text-sm leading-6">
                            <h3 className="font-medium">{finding.label}</h3>
                            <p className="text-xs leading-5 text-muted-foreground">Current selected source context; verify the proposal against this evidence.</p>
                            <blockquote className="whitespace-pre-wrap break-words border-l-2 border-blue-500 pl-3 dark:border-blue-400">
                                {finding.source.kind === "anchored" ? finding.source.quote : "Source unavailable or unbound."}
                            </blockquote>
                            <p>Limitations: {finding.limitations || "Not recorded"}</p>
                            <div className="flex flex-wrap gap-2">
                                {finding.source.kind === "anchored" && (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                            const source = finding.source;
                                            if (source.kind === "anchored") {
                                                const paper = papers.find(p => p.id === source.paper_id);
                                                if (paper) openPaper(paper, source.quote);
                                            }
                                        }}
                                    >
                                        Open proposal PDF source
                                    </Button>
                                )}
                                <Button type="button" variant="ghost" size="sm" onClick={() => setInspected(null)}>Close source context</Button>
                            </div>
                        </aside>
                    )}
                </div>
            )}
        </div>
    );
}

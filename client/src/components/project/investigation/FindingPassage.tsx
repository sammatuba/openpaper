"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { getProjectPaperFileUrl } from "@/lib/api";
import { investigationRequest, InvestigationHttpError } from "@/lib/investigation";
import type { Finding, Source } from "@/lib/investigation";
import { useProjectWorkspace } from "../ProjectWorkspaceProvider";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

const PaperPreview = dynamic(() => import("@/components/ProjectPaperPreview").then(module => module.ProjectPaperPreview), { ssr: false });
type Anchor = Extract<Source, { kind: "anchored" }>;
type Passage = { kind: "loading" } | { kind: "failed"; message: string } | { kind: "current"; text: string };

const changedPassage: Passage = { kind: "failed", message: "This passage has changed. Inspect the current lines in Evidence before using this quotation." };

export function FindingPassage({ finding }: { finding: Finding }) {
    const { projectId, papers } = useProjectWorkspace();
    const [open, setOpen] = useState(false);
    const source = finding.source;
    if (source.kind === "unbound" || (source.kind === "redacted" && !papers.some(paper => paper.id === source.paper_id))) {
        return <span className="text-xs text-muted-foreground">{source.kind === "redacted" ? "Paper passage unavailable" : "No paper passage attached"}</span>;
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            {source.kind === "redacted" && <p className="text-xs text-muted-foreground">Paper passage unavailable</p>}
            <DialogTrigger asChild>
                <Button type="button" size="sm" variant="outline">{source.kind === "anchored" ? "Open paper passage" : "Inspect paper source"}</Button>
            </DialogTrigger>
            {open && (
                <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-3xl" onKeyDown={event => event.stopPropagation()}>
                    <DialogTitle className="pr-6">{finding.label || "Untitled finding"}</DialogTitle>
                    <DialogDescription>{source.kind === "anchored"
                        ? `Paper passage, extracted lines ${source.start_line} to ${source.end_line}`
                        : "The extracted passage is unavailable."}</DialogDescription>
                    {source.kind === "redacted" ? (
                        <PassagePdf key={projectId + source.paper_id} paperId={source.paper_id} />
                    ) : <PassageBody key={[projectId, source.paper_id, source.start_line, source.end_line, source.source_sha256, source.quote_sha256].join(":")} source={source} />}
                </DialogContent>
            )}
        </Dialog>
    );
}

function PassageBody({ source }: { source: Anchor }) {
    const { projectId, papers } = useProjectWorkspace();
    const paper = papers.find(item => item.id === source.paper_id);
    const [passage, setPassage] = useState<Passage>({ kind: "loading" });
    const { paper_id, start_line, end_line, source_sha256, quote_sha256 } = source;
    useEffect(() => {
        const controller = new AbortController();
        async function readPassage(): Promise<Passage> {
            const parts: string[] = [];
            // The line endpoint serves at most 200 lines per request. Imported
            // investigations can carry longer anchors than the capture form creates.
            for (let first = start_line; first <= end_line; first += 200) {
                const count = Math.min(200, end_line - first + 1);
                const query = new URLSearchParams({ start_line: String(first), line_count: String(count) });
                const { body } = await investigationRequest(`/api/projects/${projectId}/investigation/sources/${paper_id}?${query}`, {
                    signal: controller.signal, cache: "no-store",
                });
                if (body.paper_id !== paper_id || body.source_sha256 !== source_sha256 ||
                    body.start_line !== first || body.end_line !== first + count - 1 || typeof body.text !== "string" ||
                    (first === start_line && body.end_line === end_line && body.quote_sha256 !== quote_sha256)) {
                    return changedPassage;
                }
                parts.push(body.text);
            }
            const text = parts.join("\n");
            if (text !== source.quote) return changedPassage;
            if (parts.length > 1) {
                const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
                const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
                if (hex !== quote_sha256) return changedPassage;
            }
            return { kind: "current", text };
        }
        readPassage().then(result => {
            if (!controller.signal.aborted) setPassage(result);
        }).catch(error => {
            if (controller.signal.aborted) return;
            if (error instanceof InvestigationHttpError && [413, 422].includes(error.status)) {
                setPassage(changedPassage);
                return;
            }
            const unavailable = error instanceof InvestigationHttpError && [401, 403, 404].includes(error.status);
            setPassage({ kind: "failed", message: unavailable ? "This paper passage is unavailable." : "These lines could not be opened. Inspect the source in Evidence or try again." });
        });
        return () => controller.abort();
    }, [projectId, paper_id, start_line, end_line, source_sha256, quote_sha256, source.quote]);

    return (
        <>
            <p className="font-medium">{paper?.title || source.title || "Project source"}</p>
            {passage.kind === "loading" && <p role="status">Checking the paper passage...</p>}
            {passage.kind === "failed" && <p role="alert">{passage.message}</p>}
            {passage.kind === "current" && <blockquote className="max-h-[35dvh] overflow-y-auto whitespace-pre-wrap break-words border-l-2 pl-3 text-sm">{passage.text}</blockquote>}
            <PassagePdf paperId={paper_id} searchTerm={passage.kind === "current" ? passage.text : null} />
        </>
    );
}

function PassagePdf({ paperId, searchTerm }: { paperId: string; searchTerm?: string | null }) {
    const { projectId, papers } = useProjectWorkspace();
    const paper = papers.find(item => item.id === paperId);
    const [pdfUrl, setPdfUrl] = useState<string | null>(null);
    const [loadingPdf, setLoadingPdf] = useState(false);
    const [pdfError, setPdfError] = useState(false);

    async function showPdf() {
        setLoadingPdf(true);
        setPdfError(false);
        try {
            const url = await getProjectPaperFileUrl(projectId, paperId);
            if (!url) throw new Error("PDF unavailable");
            setPdfUrl(url);
        } catch {
            setPdfError(true);
        } finally {
            setLoadingPdf(false);
        }
    }

    return (
        <>
            {pdfUrl && paper ? (
                <div className="h-[52dvh] min-h-48"><PaperPreview paper={{ ...paper, file_url: pdfUrl }} projectId={projectId} searchTerm={searchTerm} /></div>
            ) : (
                <div className="space-y-2">
                    <Button type="button" variant="outline" disabled={loadingPdf || !paper} onClick={showPdf}>{loadingPdf ? "Opening PDF..." : "View original PDF"}</Button>
                    <p className="text-xs text-muted-foreground">Check the page layout in the PDF if columns or tables read out of order.</p>
                    {pdfError && <p role="alert">The PDF could not be opened. Try again.</p>}
                </div>
            )}
        </>
    );
}

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { ArrowLeft, CircleHelp, Pencil } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProjectRole } from "@/lib/schema";
import { projectResearchBrief, RESEARCH_FRAMEWORK } from "@/lib/textfold";
import { investigationPreview } from "@/lib/investigation-preview";
import { Button } from "@/components/ui/button";
import { FoldedReader } from "@/components/fold/FoldedReader";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";
import { useInvestigation } from "@/components/project/InvestigationProvider";
import { FindingPassage } from "./investigation/FindingPassage";
import { EditProjectDialog } from "./EditProjectDialog";

// The investigation views that have a folded preview, by route.
const PAGE_VIEWS = [
    { path: "/overview", view: "case", label: "Overview preview" },
    { path: "/evidence", view: "evidence", label: "Evidence preview" },
    { path: "/draft", view: "draft", label: "Write preview" },
] as const;

// The folded document in the main workspace, reachable from every project
// route: the research brief, or the folded preview of the view on screen. It
// makes no request and no model call.
export function BriefPanel() {
    const pathname = usePathname();
    const { projectId, project, rightPanel, briefSource, openBrief, closeBrief, leaveBrief } = useProjectWorkspace();
    const { document: investigation } = useInvestigation();
    const [editing, setEditing] = useState(false);
    const shown = rightPanel === "brief";
    const page = PAGE_VIEWS.find(item => pathname === `/projects/${projectId}${item.path}`);
    const source = briefSource === "page" && page ? "page" : "brief";

    const brief = useMemo(() => (shown && project ? projectResearchBrief(project) : null), [shown, project]);
    const preview = useMemo(
        () => (shown && source === "page" && page ? investigationPreview(investigation, page.view, projectId) : null),
        [shown, source, page, investigation, projectId],
    );

    const findingsById = useMemo(() => new Map(investigation.findings.map(finding => [finding.id, finding])), [investigation.findings]);

    const panel = useRef<HTMLElement>(null);
    const visible = shown && Boolean(project && brief);
    useEffect(() => {
        if (visible) panel.current?.focus({ preventScroll: true });
    }, [visible]);

    if (!shown || !project || !brief) return null;

    const canEdit = project.role === ProjectRole.Admin;
    const doc = brief.document;
    const hasContent = doc.sections.some(section => section.units.length > 0);
    const missing = RESEARCH_FRAMEWORK.filter(item => !doc.sections.some(section => item.match.test(section.title) && section.units.some(unit => unit.full.trim())));
    const tab = (active: boolean) => cn(
        "rounded-md px-2.5 py-1 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
        active ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
    );

    return (
        <section
            ref={panel}
            tabIndex={-1}
            aria-label="Folded reading view"
            data-brief-panel={source}
            onKeyDown={event => { if (event.key === "Escape" && !event.defaultPrevented && !editing) closeBrief(); }}
            onClick={event => {
                if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey &&
                    (event.target as HTMLElement).closest('a[href^="/"]:not([target]), a[href^="/"][target="_self"]')) leaveBrief();
            }}
            className="workspace-panel flex min-h-0 min-w-0 flex-1 flex-col bg-background outline-none"
        >
            <div className="flex shrink-0 flex-wrap items-center gap-1 border-b px-3 py-1.5 sm:px-5">
                <div role="group" aria-label="Document" className="flex min-w-0 items-center gap-0.5">
                    <button type="button" aria-pressed={source === "brief"} className={tab(source === "brief")} onClick={() => openBrief("brief")}>Research brief</button>
                    {page && <button type="button" aria-pressed={source === "page"} className={tab(source === "page")} onClick={() => openBrief("page")}>{page.label}</button>}
                </div>
                <div className="ml-auto flex shrink-0 items-center gap-1">
                    {canEdit && source === "brief" && (
                        <Button variant="outline" size="sm" className="h-7 gap-1.5 px-2 text-xs" onClick={() => setEditing(true)}>
                            <Pencil aria-hidden className="h-3 w-3" />Edit brief
                        </Button>
                    )}
                    <Button variant="ghost" size="sm" className="h-8 gap-1 px-2" aria-label="Back to workspace" onClick={closeBrief}>
                        <ArrowLeft aria-hidden className="h-4 w-4" />Back
                    </Button>
                </div>
            </div>

            {source === "brief" && brief.invalid && (
                <p role="alert" className="shrink-0 border-b px-4 py-2 text-sm">The saved reading levels could not be opened. Showing the project description. Edit the brief to replace the imported levels.</p>
            )}

            <div className="min-h-0 flex-1">
                {source === "page" && preview && page && (
                    <FoldedReader
                        key={`${projectId}:${page.view}`}
                        document={preview}
                        label="Folded document preview"
                        literalText={page.view === "evidence"}
                        sectionAction={page.view === "evidence" ? id => {
                            const finding = findingsById.get(id);
                            return finding && <FindingPassage finding={finding} />;
                        } : undefined}
                        findingHref={id => investigation.findings.some(finding => finding.id === id) ? `/projects/${projectId}/evidence?finding=${id}` : null}
                    />
                )}
                {source === "brief" && hasContent && (
                    <FoldedReader
                        key={project.id}
                        document={doc}
                        label="Folded research brief"
                        exportable
                        footer={
                            <div className="space-y-4 border-t pt-4">
                                {missing.length > 0 && (
                                    <details className="text-sm">
                                        <summary className="cursor-pointer font-medium">Open questions in this brief · {missing.length} areas to develop</summary>
                                        <p className="mt-3 text-xs leading-5 text-muted-foreground">Based on section headings only. A missing section is a writing gap, not a finding about the research.</p>
                                        <ul className="mt-3 space-y-3">
                                            {missing.map(item => <li key={item.key}><span className="text-xs font-medium">{item.title}</span><p className="mt-1 text-xs leading-5 text-muted-foreground">{item.prompt}</p></li>)}
                                        </ul>
                                    </details>
                                )}
                                <p className="text-xs leading-5 text-muted-foreground">
                                    Organized around a disputed question, following <a href="https://www.lesswrong.com/posts/tn4WSyrqr7ozGLjRy/people-should-resolve-tensions-in-ai-safety-research" className="underline" target="_blank" rel="noopener noreferrer">David Africa’s research-tension framework</a>. These are project statements; literature coverage and novelty need source-backed review.
                                </p>
                            </div>
                        }
                    />
                )}
                {source === "brief" && !hasContent && (
                    <div className="m-4 rounded-xl border border-dashed p-6">
                        <CircleHelp aria-hidden className="mb-3 h-5 w-5 text-muted-foreground" />
                        <h2 className="mb-2 font-medium">Start with the uncertainty</h2>
                        <p className="text-sm leading-6 text-muted-foreground">What question could this project help resolve? Add a research brief to connect the evidence, explain disagreements and identify the next useful experiment.</p>
                        {canEdit && <Button variant="outline" size="sm" className="mt-4" onClick={() => setEditing(true)}>Write a research brief</Button>}
                    </div>
                )}
            </div>
            {canEdit && <EditProjectDialog open={editing} onOpenChange={setEditing} />}
        </section>
    );
}

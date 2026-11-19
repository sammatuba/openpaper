"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { CircleHelp, Maximize2, Minimize2, Pencil, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProjectRole } from "@/lib/schema";
import { projectResearchBrief, RESEARCH_FRAMEWORK } from "@/lib/textfold";
import { investigationPreview } from "@/lib/investigation-preview";
import { Button } from "@/components/ui/button";
import { FoldedReader } from "@/components/fold/FoldedReader";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";
import { useInvestigation } from "@/components/project/InvestigationProvider";
import { EditProjectDialog } from "./EditProjectDialog";

// The investigation views that have a folded preview, by route.
const PAGE_VIEWS = [
    { path: "/overview", view: "case", label: "Overview preview" },
    { path: "/evidence", view: "evidence", label: "Evidence preview" },
    { path: "/draft", view: "draft", label: "Write preview" },
] as const;

// The folded brief in the workspace's right slot, reachable from every project
// route: the research brief, or the folded preview of the view on screen. It
// makes no request and no model call.
export function BriefPanel() {
    const pathname = usePathname();
    const { projectId, project, rightPanel, briefSource, openBrief, closeBrief } = useProjectWorkspace();
    const { document: investigation } = useInvestigation();
    const [wide, setWide] = useState(false);
    const [editing, setEditing] = useState(false);
    const shown = rightPanel === "brief";
    const page = PAGE_VIEWS.find(item => pathname === `/projects/${projectId}${item.path}`);
    const source = briefSource === "page" && page ? "page" : "brief";

    const brief = useMemo(() => (shown && project ? projectResearchBrief(project) : null), [shown, project]);
    const preview = useMemo(
        () => (shown && source === "page" && page ? investigationPreview(investigation, page.view, projectId) : null),
        [shown, source, page, investigation, projectId],
    );

    // Opening moves focus into the panel; closing returns it to whatever opened it.
    const panel = useRef<HTMLElement>(null);
    const opener = useRef<HTMLElement | null>(null);
    const wasShown = useRef(false);
    // Set by the panel's own Close and Escape. When another panel takes the slot, or a link
    // navigates away, focus stays where the user put it.
    const returnFocus = useRef(false);
    useEffect(() => {
        if (shown && !wasShown.current) {
            opener.current = document.activeElement as HTMLElement;
            panel.current?.focus({ preventScroll: true });
        }
        if (!shown && wasShown.current && returnFocus.current && opener.current?.isConnected) opener.current.focus();
        returnFocus.current = false;
        wasShown.current = shown;
    }, [shown]);
    const close = () => { returnFocus.current = true; closeBrief(); };

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
        <aside
            ref={panel}
            tabIndex={-1}
            aria-label="Research brief panel"
            data-brief-panel={source}
            onKeyDown={event => { if (event.key === "Escape" && !event.defaultPrevented && !editing) close(); }}
            // Below the desktop layout the panel covers the page, so following a link out of it (a cited finding) closes it.
            onClick={event => { if ((event.target as HTMLElement).closest('a[href^="/"]') && window.innerWidth < 1024) closeBrief(); }}
            className={cn(
                "workspace-panel fixed inset-0 z-40 flex flex-col bg-background outline-none lg:static lg:z-auto lg:shrink-0 lg:border-l",
                wide ? "lg:w-[72%]" : "lg:w-[56%] lg:min-w-[440px] lg:max-w-[980px]",
            )}
        >
            <div className="flex h-11 shrink-0 items-center gap-2 border-b px-3">
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
                    <Button variant="ghost" size="icon" className="hidden h-7 w-7 lg:inline-flex" aria-pressed={wide} aria-label={wide ? "Narrow the panel" : "Widen the panel"} onClick={() => setWide(!wide)}>
                        {wide ? <Minimize2 aria-hidden className="h-4 w-4" /> : <Maximize2 aria-hidden className="h-4 w-4" />}
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Close research brief panel" onClick={close}>
                        <X aria-hidden className="h-4 w-4" />
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
        </aside>
    );
}

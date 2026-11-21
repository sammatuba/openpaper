"use client";

import { ReactNode, useEffect } from "react";
import { useParams } from "next/navigation";
import {
    ProjectWorkspaceProvider,
    useProjectWorkspace,
} from "@/components/project/ProjectWorkspaceProvider";
import { ProjectHeader } from "@/components/project/ProjectHeader";
import { ProjectRail } from "@/components/project/ProjectRail";
import { Deferred } from "@/components/project/Deferred";
import { InvestigationProvider } from "@/components/project/InvestigationProvider";
import { WorkspaceBar } from "@/components/project/investigation/WorkspaceBar";
import PdfUploadTracker from "@/components/PdfUploadTracker";

// The right-slot panels and the add-papers sheet are fetched when first needed,
// so a project opens without their code or their requests.
const loadReader = () => import("@/components/project/ReaderPanel").then(module => module.ReaderPanel);
const loadBrief = () => import("@/components/project/BriefPanel").then(module => module.BriefPanel);
const loadArtifacts = () => import("@/components/project/ArtifactsPanel").then(module => module.ArtifactsPanel);
const loadAddPapers = () => import("@/components/project/AddPapersSheet").then(module => module.AddPapersSheet);

// Shared workspace shell for every project route: breadcrumb header on top,
// papers + chats rail on the left, route content in the middle, and the
// on-demand reader panel on the right. Reader tabs, the artifacts drawer, and
// in-flight uploads persist across navigation within the project.
function WorkspaceShell({ children }: { children: ReactNode }) {
    const {
        project, projectError, projectDenied, uploadJobs, refetchPapers, railCollapsed, rightPanel, openPaperIds, addPapersOpen,
        closeReader, closeBrief, closeArtifacts, setAddPapersOpen,
    } = useProjectWorkspace();

    // Fetch the panels' code once the project is on screen and the page is idle,
    // so the first open does not wait on the network and loading the project
    // does not compete with it. Skipped when the browser asks to save data.
    const ready = project !== null;
    // A project that cannot be shown: the rail, the panels and the sheet are
    // unmounted, so nothing they had loaded stays on screen or in the page.
    const denied = projectDenied;
    useEffect(() => {
        if (!ready) return;
        const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
        if (connection?.saveData) return;
        const warm = () => {
            for (const load of [loadBrief, loadReader, loadArtifacts, loadAddPapers]) load().catch(() => undefined);
        };
        if (typeof window.requestIdleCallback === "function") {
            const handle = window.requestIdleCallback(warm, { timeout: 4000 });
            return () => window.cancelIdleCallback(handle);
        }
        const timer = window.setTimeout(warm, 2000);
        return () => window.clearTimeout(timer);
    }, [ready]);

    return (
        // Full viewport height — the app-shell header hides itself on project routes.
        <div className="flex h-svh flex-col overflow-hidden">
            <ProjectHeader />
            <div className="flex min-h-0 flex-1">
                {!railCollapsed && !denied && (
                    <aside className="hidden border-r md:flex">
                        <ProjectRail />
                    </aside>
                )}
                <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
                    <WorkspaceBar />
                    {uploadJobs.length > 0 && !denied && (
                        <div className="shrink-0 px-4 pt-3">
                            <PdfUploadTracker initialJobs={uploadJobs} onComplete={refetchPapers} />
                        </div>
                    )}
                    {/* A project that cannot be shown replaces every view. The bar above stays, so unsaved work can still be downloaded. */}
                    {denied
                        ? <div role="alert" data-project-error className="p-4 text-destructive">{projectError?.message}</div>
                        : children}
                </main>
                {/* Right slot: reader, artifacts and the folded brief share it, one visible at a time */}
                {!denied && <>
                <Deferred load={loadReader} wanted={openPaperIds.length > 0} shown={rightPanel === "reader" && openPaperIds.length > 0} label="paper reader" onDismiss={closeReader} />
                <Deferred load={loadBrief} wanted={rightPanel === "brief"} shown={rightPanel === "brief"} label="research brief" onDismiss={closeBrief} />
                <Deferred load={loadArtifacts} wanted={rightPanel === "artifacts"} shown={rightPanel === "artifacts"} label="artifacts panel" onDismiss={closeArtifacts} />
                </>}
            </div>
            {!denied && <Deferred load={loadAddPapers} wanted={addPapersOpen} shown={addPapersOpen} label="add papers form" onDismiss={() => setAddPapersOpen(false)} />}
        </div>
    );
}

export default function ProjectWorkspaceLayout({ children }: { children: ReactNode }) {
    const params = useParams();
    const projectId = params.projectId as string;

    return (
        <ProjectWorkspaceProvider projectId={projectId}>
            <InvestigationProvider key={projectId}><WorkspaceShell>{children}</WorkspaceShell></InvestigationProvider>
        </ProjectWorkspaceProvider>
    );
}

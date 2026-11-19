"use client";

import {
    createContext,
    ReactNode,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import { fetchFromApi, getProjectPaperFileUrl } from "@/lib/api";
import { withTransition } from "@/lib/transition";
import { isGone } from "@/lib/reads";
import { Conversation, MinimalJob, PaperItem, Project } from "@/lib/schema";
import {
    useProject,
    useProjectConversations,
    useProjectPapers,
} from "@/hooks/useProjects";

// What the right pane is currently showing: paper reader tabs, the artifacts
// panel, the folded brief, or nothing (collapsed).
export type RightPanelMode = "reader" | "artifacts" | "brief" | null;

// What the brief panel shows: the project's research brief, or the folded
// preview of the investigation view on screen.
export type BriefSource = "brief" | "page";

// Which view the add-papers sheet opens on. "initial" is the chooser;
// callers that already know the user's intent deep-link to upload/library.
export type AddPapersView = "initial" | "upload" | "library";

interface ProjectWorkspaceValue {
    projectId: string;
    // Shared data — fetched once for all project routes (rail, header, pages).
    project: Project | null;
    isProjectLoading: boolean;
    projectError: Error | null;
    // The project is gone or no longer ours to read (401, 403, 404). A plain
    // failure to load is not this: the workspace keeps its usual error states.
    projectDenied: boolean;
    refetchProject: () => Promise<void>;
    papers: PaperItem[];
    isPapersLoading: boolean;
    refetchPapers: () => Promise<void>;
    updatePaper: (paperId: string, patch: Partial<PaperItem>) => void;
    conversations: Conversation[];
    isConversationsLoading: boolean;
    refetchConversations: () => Promise<void>;
    // In-page reader panel (open papers as tabs).
    openPaperIds: string[];
    activePaperId: string | null;
    readerSearchTerm: string | null;
    openPaper: (paper: PaperItem, searchTerm?: string | null) => void;
    activatePaper: (paperId: string) => void;
    closePaper: (paperId: string) => void;
    closeReader: () => void;
    // Fetch a fresh presigned file URL and patch it into the papers list.
    refreshPaperUrl: (paperId: string) => Promise<string | null>;
    // Workspace chrome state.
    crumb: string | null;
    setCrumb: (crumb: string | null) => void;
    rightPanel: RightPanelMode;
    briefSource: BriefSource;
    openBrief: (source?: BriefSource) => void;
    toggleBrief: () => void;
    closeBrief: () => void;
    toggleArtifacts: () => void;
    closeArtifacts: () => void;
    // Transient collapse (e.g. on sending a chat message): hides the artifacts
    // panel for now but, unlike closeArtifacts, does NOT persist the preference,
    // so the panel returns to its default-open state next session.
    collapseArtifacts: () => void;
    railCollapsed: boolean;
    toggleRail: () => void;
    addPapersOpen: boolean;
    setAddPapersOpen: (open: boolean) => void;
    addPapersInitialView: AddPapersView;
    // Open the sheet on a specific view ("upload"/"library") when the caller
    // already knows the user's intent; defaults to the chooser.
    openAddPapers: (view?: AddPapersView) => void;
    hasCollaborators: boolean;
    setHasCollaborators: (has: boolean) => void;
    // In-flight PDF upload jobs surfaced by PdfUploadTracker in the layout.
    uploadJobs: MinimalJob[];
    addUploadJobs: (jobs: MinimalJob[]) => void;
    // A discussion's first prompt, handed from the page that starts it to the
    // conversation page. Held in memory only: research text is never written
    // to browser storage.
    pendingDiscussions: { current: Map<string, PendingDiscussion> };
}

export interface PendingDiscussion {
    query: string;
    paperIds: string[];
}

const NO_PAPERS: PaperItem[] = [];
const NO_CONVERSATIONS: Conversation[] = [];
const NO_IDS: string[] = [];
const NO_JOBS: MinimalJob[] = [];

const ProjectWorkspaceContext = createContext<ProjectWorkspaceValue | null>(null);

export function useProjectWorkspace(): ProjectWorkspaceValue {
    const context = useContext(ProjectWorkspaceContext);
    if (!context) {
        throw new Error("useProjectWorkspace must be used within a ProjectWorkspaceProvider");
    }
    return context;
}

interface ProjectWorkspaceProviderProps {
    projectId: string;
    children: ReactNode;
}

export function ProjectWorkspaceProvider({ projectId, children }: ProjectWorkspaceProviderProps) {
    const { project, isLoading: isProjectLoading, error: projectError, refetch: refetchProject } = useProject(projectId);
    const { papers, isLoading: isPapersLoading, refetch: refetchPapers, updatePaper } = useProjectPapers(projectId);
    const { conversations, isLoading: isConversationsLoading, refetch: refetchConversations } = useProjectConversations(projectId);

    const [openPaperIds, setOpenPaperIds] = useState<string[]>([]);
    const [activePaperId, setActivePaperId] = useState<string | null>(null);
    const [readerSearchTerm, setReaderSearchTerm] = useState<string | null>(null);
    const [crumb, setCrumb] = useState<string | null>(null);
    // Leave room for research work on a first visit. Honor an explicit desktop
    // preference; mobile never starts with a full-screen artifacts overlay.
    const [rightPanel, setRightPanel] = useState<RightPanelMode>(() => {
        if (typeof window === "undefined") return null;
        if (window.innerWidth < 768) return null;
        return localStorage.getItem("project-artifacts-collapsed") === "false" ? "artifacts" : null;
    });
    // Desktop rail collapse, persisted across sessions.
    const [railCollapsed, setRailCollapsed] = useState<boolean>(() => {
        if (typeof window === "undefined") return false;
        return localStorage.getItem("project-rail-collapsed") === "true";
    });
    const [addPapersOpen, setAddPapersOpen] = useState(false);
    const [addPapersInitialView, setAddPapersInitialView] = useState<AddPapersView>("initial");
    const [hasCollaborators, setHasCollaborators] = useState(false);
    const [uploadJobs, setUploadJobs] = useState<MinimalJob[]>([]);

    // The panel on screen, for handlers that must act at the click. A panel
    // change is applied a frame later, inside the transition; a preference
    // written only there would be lost if the page were left in that frame.
    const shownPanel = useRef(rightPanel);
    shownPanel.current = rightPanel;
    // Whether the artifacts panel was last asked to be open, while that request
    // is still on its way to the state. Lets two quick toggles save the right preference.
    // It is kept until every change asked for has been applied, whatever renders in between.
    const artifactsAsked = useRef<{ open: boolean; pending: number } | null>(null);
    const askArtifacts = useCallback((open: boolean) => {
        artifactsAsked.current = { open, pending: (artifactsAsked.current?.pending ?? 0) + 1 };
        localStorage.setItem("project-artifacts-collapsed", String(!open));
    }, []);
    const artifactsApplied = useCallback(() => {
        const asked = artifactsAsked.current;
        if (asked && --asked.pending <= 0) artifactsAsked.current = null;
    }, []);
    const artifactsOpen = useCallback(() => artifactsAsked.current?.open ?? shownPanel.current === "artifacts", []);

    // A change of what the right slot shows, animated where the browser can.
    const movePanel = useCallback((next: (mode: RightPanelMode) => RightPanelMode, applied?: () => void) => {
        withTransition(() => {
            setRightPanel(next);
            // After React has rendered the change: at once inside a transition, a microtask later without one.
            if (applied) queueMicrotask(applied);
        });
    }, []);

    const openPaper = useCallback((paper: PaperItem, searchTerm: string | null = null) => {
        withTransition(() => {
            setOpenPaperIds((prev) => (prev.includes(paper.id) ? prev : [...prev, paper.id]));
            setActivePaperId(paper.id);
            setReaderSearchTerm(searchTerm);
            setRightPanel("reader");
        });
    }, []);

    const activatePaper = useCallback((paperId: string) => {
        setActivePaperId(paperId);
        // A manual tab switch shouldn't replay a stale citation search.
        setReaderSearchTerm(null);
        setRightPanel("reader");
    }, []);

    const closePaper = useCallback((paperId: string) => {
        withTransition(() => {
            setOpenPaperIds((prev) => {
                const next = prev.filter((id) => id !== paperId);
                setActivePaperId((active) => (active === paperId ? (next[next.length - 1] ?? null) : active));
                if (next.length === 0) {
                    setRightPanel((mode) => (mode === "reader" ? null : mode));
                }
                return next;
            });
        });
    }, []);

    const closeReader = useCallback(() => {
        withTransition(() => {
            setOpenPaperIds([]);
            setActivePaperId(null);
            setReaderSearchTerm(null);
            setRightPanel((mode) => (mode === "reader" ? null : mode));
        });
    }, []);

    const toggleArtifacts = useCallback(() => {
        askArtifacts(!artifactsOpen());
        movePanel((mode) => {
            if (mode === "artifacts") {
                localStorage.setItem("project-artifacts-collapsed", "true");
                // Fall back to the reader when paper tabs are still open.
                return openPaperIds.length > 0 ? "reader" : null;
            }
            localStorage.setItem("project-artifacts-collapsed", "false");
            return "artifacts";
        }, artifactsApplied);
    }, [openPaperIds.length, movePanel, askArtifacts, artifactsApplied, artifactsOpen]);

    const closeArtifacts = useCallback(() => {
        if (!artifactsOpen()) return;
        askArtifacts(false);
        movePanel((mode) => {
            if (mode !== "artifacts") return mode;
            localStorage.setItem("project-artifacts-collapsed", "true");
            return openPaperIds.length > 0 ? "reader" : null;
        }, artifactsApplied);
    }, [openPaperIds.length, movePanel, askArtifacts, artifactsApplied, artifactsOpen]);

    // Get the artifacts panel out of the way (e.g. when sending a chat message)
    // without changing the user's saved preference.
    const collapseArtifacts = useCallback(() => {
        movePanel((mode) => {
            if (mode !== "artifacts") return mode;
            return openPaperIds.length > 0 ? "reader" : null;
        });
    }, [openPaperIds.length]);

    const [briefSource, setBriefSource] = useState<BriefSource>("brief");
    const openBrief = useCallback((source: BriefSource = "brief") => {
        withTransition(() => {
            setBriefSource(source);
            setRightPanel("brief");
        });
    }, []);
    // Closing the brief gives the slot back to open paper tabs, as the artifacts panel does.
    const closeBrief = useCallback(() => {
        movePanel((mode) => (mode !== "brief" ? mode : openPaperIds.length > 0 ? "reader" : null));
    }, [openPaperIds.length]);
    const toggleBrief = useCallback(() => {
        movePanel((mode) => (mode !== "brief" ? "brief" : openPaperIds.length > 0 ? "reader" : null));
    }, [openPaperIds.length]);

    const openAddPapers = useCallback((view: AddPapersView = "initial") => {
        setAddPapersInitialView(view);
        setAddPapersOpen(true);
    }, []);

    const toggleRail = useCallback(() => {
        setRailCollapsed((prev) => {
            const next = !prev;
            localStorage.setItem("project-rail-collapsed", String(next));
            return next;
        });
    }, []);

    const refreshPaperUrl = useCallback(async (paperId: string): Promise<string | null> => {
        try {
            const fileUrl = await getProjectPaperFileUrl(projectId, paperId);
            if (fileUrl) {
                updatePaper(paperId, { file_url: fileUrl });
                return fileUrl;
            }
            return null;
        } catch (error) {
            console.error("Error refreshing paper URL:", error);
            return null;
        }
    }, [projectId, updatePaper]);

    const pendingDiscussions = useRef(new Map<string, PendingDiscussion>());
    const addUploadJobs = useCallback((jobs: MinimalJob[]) => {
        setUploadJobs((prev) => [...prev, ...jobs]);
    }, []);

    // Rehydrate the upload tracker after a refresh: in-flight jobs are
    // otherwise only held in local state and lost on navigation.
    useEffect(() => {
        if (!projectId) return;
        let cancelled = false;
        (async () => {
            try {
                const response = await fetchFromApi(`/api/projects/papers/${projectId}/pending-jobs`);
                if (cancelled || !response?.jobs?.length) return;
                const restoredJobs: MinimalJob[] = response.jobs.map((job: { job_id: string; title: string | null }) => ({
                    jobId: job.job_id,
                    fileName: job.title || "Uploading paper…",
                }));
                setUploadJobs((prevJobs) => {
                    const known = new Set(prevJobs.map((j) => j.jobId));
                    const newOnes = restoredJobs.filter((j) => !known.has(j.jobId));
                    return newOnes.length ? [...prevJobs, ...newOnes] : prevJobs;
                });
            } catch (err) {
                console.error("Failed to fetch pending upload jobs for project", err);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [projectId]);

    // A project that cannot be shown takes what was loaded with it: no papers,
    // no chats, no open panel. Views and panels then have nothing of it to show.
    const denied = project === null && isGone(projectError);
    const shown = useMemo(
        () => (denied
            ? { papers: NO_PAPERS, conversations: NO_CONVERSATIONS, openPaperIds: NO_IDS, rightPanel: null as RightPanelMode, uploadJobs: NO_JOBS }
            : { papers, conversations, openPaperIds, rightPanel, uploadJobs }),
        [denied, papers, conversations, openPaperIds, rightPanel, uploadJobs],
    );

    const value = useMemo<ProjectWorkspaceValue>(() => ({
        projectId,
        project,
        isProjectLoading,
        projectError,
        projectDenied: denied,
        refetchProject,
        papers: shown.papers,
        isPapersLoading,
        refetchPapers,
        updatePaper,
        conversations: shown.conversations,
        isConversationsLoading,
        refetchConversations,
        openPaperIds: shown.openPaperIds,
        activePaperId,
        readerSearchTerm,
        openPaper,
        activatePaper,
        closePaper,
        closeReader,
        refreshPaperUrl,
        crumb,
        setCrumb,
        rightPanel: shown.rightPanel,
        briefSource,
        openBrief,
        toggleBrief,
        closeBrief,
        toggleArtifacts,
        closeArtifacts,
        collapseArtifacts,
        railCollapsed,
        toggleRail,
        addPapersOpen,
        setAddPapersOpen,
        addPapersInitialView,
        openAddPapers,
        hasCollaborators,
        setHasCollaborators,
        uploadJobs: shown.uploadJobs,
        addUploadJobs,
        pendingDiscussions,
    }), [
        projectId, project, isProjectLoading, projectError, refetchProject,
        papers, isPapersLoading, refetchPapers, updatePaper,
        conversations, isConversationsLoading, refetchConversations,
        openPaperIds, activePaperId, readerSearchTerm,
        openPaper, activatePaper, closePaper, closeReader, refreshPaperUrl,
        crumb, rightPanel, briefSource, openBrief, toggleBrief, closeBrief, toggleArtifacts, closeArtifacts, collapseArtifacts, railCollapsed, toggleRail,
        addPapersOpen, addPapersInitialView, openAddPapers, hasCollaborators,
        uploadJobs, addUploadJobs, shown,
    ]);

    return (
        <ProjectWorkspaceContext.Provider value={value}>
            {children}
        </ProjectWorkspaceContext.Provider>
    );
}

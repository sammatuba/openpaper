"use client";

import { useCallback, useMemo, useState, useSyncExternalStore } from "react";
import useSWR, { mutate as mutateCache } from "swr";
import { fetchFromApi } from "@/lib/api";
import { createReads, isGone } from "@/lib/reads";
import { forgetInvestigation, forgetInvestigations } from "@/lib/investigation-snapshot";
import { Project, PaperItem, Conversation } from "@/lib/schema";

// Project data is read through SWR: a cached value renders at once and is
// revalidated behind it, so returning to a project does not show a skeleton.
// The rules that keep a cached copy from outliving the user's access to it are
// in lib/reads.ts.

const projectKey = (projectId: string) => `/api/projects/${projectId}`;
const papersKey = (projectId: string, loadUrls = false) =>
    `/api/projects/papers/${projectId}${loadUrls ? "?load_urls=true" : ""}`;
const conversationsKey = (projectId: string) => `/api/projects/conversations/${projectId}`;

// A project that is denied takes its kept investigation with it, whether a mounted workspace or a card's
// prefetch learned of the denial.
// A denial can also be recorded, or lifted, by a request the hook showing it did not make (a card's
// prefetch), and SWR does not re-render a hook whose data came back unchanged. So the hooks subscribe to
// the denials themselves.
let denialsVersion = 0;
const denialWatchers = new Set<() => void>();
const subscribeDenials = (watcher: () => void) => { denialWatchers.add(watcher); return () => { denialWatchers.delete(watcher); }; };
const useDenials = () => useSyncExternalStore(subscribeDenials, () => denialsVersion, () => 0);
const reads = createReads(fetchFromApi, {
    denied: url => {
        // The project itself, not its paper list or discussions: a refusal of those alone leaves the
        // investigation's own request to say whether it may be read.
        const project = /^\/api\/projects\/([^/?]+)$/.exec(url)?.[1];
        if (project) forgetInvestigation(project);
    },
    changed: () => {
        denialsVersion += 1;
        for (const watcher of [...denialWatchers]) watcher();
    },
});
const asJson = <T,>(body: unknown) => body as T;
const asList = <T,>(body: unknown) => ((body as T[] | null) || []);
const asPapers = (body: unknown) => (body as { papers?: PaperItem[] } | null)?.papers || [];

const fetchJson = <T,>(url: string) => reads.read(url, asJson<T>);
const fetchList = <T,>(url: string) => reads.read(url, asList<T>);
const fetchPapers = (url: string) => reads.read(url, asPapers);

// Retrying cannot bring back something that is gone.
const OPTIONS = { shouldRetryOnError: (error: unknown) => !isGone(error) };

// A failed revalidation keeps the cached value on screen. The error surfaces
// when there is nothing to show, or while the resource stands denied.
function settle<T>(key: string | null, data: T | undefined, error: unknown, what: string): { data: T | undefined; error: Error | null } {
    const denied = key ? reads.denied(key) : null;
    if (denied) return { data: undefined, error: denied };
    if (!error || data !== undefined) return { data, error: null };
    return { data: undefined, error: error instanceof Error ? error : new Error(`Failed to fetch ${what}`) };
}

// Fetch a project's data ahead of opening it (pointer or focus on its card).
// A successful response goes into the cache, and the workspace still
// revalidates when it mounts. SWR's own preload is not used: it holds a
// response until the next fetch consumes it, however much later that is.
const warmedAt = new Map<string, number>();
export function preloadProject(projectId: string) {
    const now = Date.now();
    if (now - (warmedAt.get(projectId) ?? 0) < 30_000) return;
    warmedAt.set(projectId, now);
    const write = (key: string, data: unknown) => { void mutateCache(key, data, { revalidate: false }); };
    void reads.prefetch(projectKey(projectId), asJson<Project>, write);
    void reads.prefetch(papersKey(projectId), asPapers, write);
    void reads.prefetch(conversationsKey(projectId), asList<Conversation>, write);
}

// Signing out: cached responses belong to the user who left, and a response
// still on its way must not land in the next user's cache.
export async function endProjectSession() {
    reads.end();
    forgetInvestigations();
    warmedAt.clear();
    await mutateCache(() => true, undefined, { revalidate: false });
}

interface UseProjectsResult {
    projects: Project[];
    isLoading: boolean;
    error: Error | null;
    refetch: () => Promise<void>;
}

const NO_PROJECTS: Project[] = [];
const NO_PAPERS: PaperItem[] = [];
const NO_CONVERSATIONS: Conversation[] = [];

export function useProjects(detailed = false): UseProjectsResult {
    // detailed=true includes metadata (num_papers, num_conversations, …)
    // that the plain list omits.
    const key = detailed ? "/api/projects?detailed=true" : "/api/projects";
    const swr = useSWR<Project[]>(key, fetchList<Project>, OPTIONS);
    useDenials();
    const { data, error } = settle(key, swr.data, swr.error, "projects");
    const { mutate } = swr;
    const refetch = useCallback(async () => { await mutate().catch(() => undefined); }, [mutate]);

    return { projects: data ?? NO_PROJECTS, isLoading: swr.isLoading, error, refetch };
}

interface UseProjectResult {
    project: Project | null;
    isLoading: boolean;
    error: Error | null;
    refetch: () => Promise<void>;
}

export function useProject(projectId?: string): UseProjectResult {
    const key = projectId ? projectKey(projectId) : null;
    const swr = useSWR<Project>(key, fetchJson<Project>, OPTIONS);
    useDenials();
    const { data, error } = settle(key, swr.data, swr.error, `project ${projectId}`);
    const { mutate } = swr;
    const refetch = useCallback(async () => { await mutate().catch(() => undefined); }, [mutate]);

    return { project: data ?? null, isLoading: swr.isLoading, error, refetch };
}

interface UseProjectPapersOptions {
    // Whether the list endpoint should also generate presigned file URLs.
    // Defaults to false — most consumers only need paper metadata, and URL
    // generation is expensive. Consumers that need a URL for a single paper
    // should fetch it lazily via getProjectPaperFileUrl instead.
    loadUrls?: boolean;
}

interface UseProjectPapersResult {
    papers: PaperItem[];
    isLoading: boolean;
    error: Error | null;
    refetch: () => Promise<void>;
    // Locally patch a single paper (e.g. to inject a refreshed file_url)
    // without refetching the whole list.
    updatePaper: (paperId: string, patch: Partial<PaperItem>) => void;
}

type Patches = { projectId?: string; byPaper: Record<string, Partial<PaperItem>> };

export function useProjectPapers(
    projectId?: string,
    options?: UseProjectPapersOptions,
): UseProjectPapersResult {
    const loadUrls = options?.loadUrls ?? false;
    const key = projectId ? papersKey(projectId, loadUrls) : null;
    const swr = useSWR<PaperItem[]>(key, fetchPapers, OPTIONS);
    useDenials();
    const { data, error } = settle(key, swr.data, swr.error, `papers for project ${projectId}`);
    const { mutate } = swr;
    const refetch = useCallback(async () => { await mutate().catch(() => undefined); }, [mutate]);

    // Local patches sit over the fetched list, not in the cache, so a
    // revalidation does not drop them: an open reader keeps its file URL.
    const [patches, setPatches] = useState<Patches>({ projectId, byPaper: {} });
    const updatePaper = useCallback((paperId: string, patch: Partial<PaperItem>) => {
        setPatches(previous => {
            const byPaper = previous.projectId === projectId ? previous.byPaper : {};
            return { projectId, byPaper: { ...byPaper, [paperId]: { ...byPaper[paperId], ...patch } } };
        });
    }, [projectId]);
    const papers = useMemo(() => {
        if (!data) return NO_PAPERS;
        if (patches.projectId !== projectId) return data;
        return data.map(paper => (patches.byPaper[paper.id] ? { ...paper, ...patches.byPaper[paper.id] } : paper));
    }, [data, patches, projectId]);

    return { papers, isLoading: swr.isLoading, error, refetch, updatePaper };
}

interface UseProjectConversationsResult {
    conversations: Conversation[];
    isLoading: boolean;
    error: Error | null;
    refetch: () => Promise<void>;
}

export function useProjectConversations(projectId?: string): UseProjectConversationsResult {
    const key = projectId ? conversationsKey(projectId) : null;
    const swr = useSWR<Conversation[]>(key, fetchList<Conversation>, OPTIONS);
    useDenials();
    const { data, error } = settle(key, swr.data, swr.error, `conversations for project ${projectId}`);
    const { mutate } = swr;
    const refetch = useCallback(async () => { await mutate().catch(() => undefined); }, [mutate]);

    return { conversations: data ?? NO_CONVERSATIONS, isLoading: swr.isLoading, error, refetch };
}

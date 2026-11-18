"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, CircleDot, Compass, Download, FileUp, Loader2, MessagesSquare, MoreHorizontal, PenLine, Scale } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { downloadInvestigation, investigationRequest } from "@/lib/investigation";
import type { Investigation } from "@/lib/investigation";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";
import { useInvestigation } from "@/components/project/InvestigationProvider";
import { useCanEdit } from "./shared";

const DESTINATIONS: { key: string; label: string; path: string; icon: LucideIcon }[] = [
    { key: "overview", label: "Overview", path: "", icon: Compass },
    { key: "evidence", label: "Evidence", path: "/evidence", icon: Scale },
    { key: "write", label: "Write", path: "/draft", icon: PenLine },
    { key: "discuss", label: "Discuss", path: "/discuss", icon: MessagesSquare },
];

const EXPORT_EXTENSION = { markdown: "md", bibtex: "bib", bundle: "json" } as const;

function SaveState({ status }: { status: string }) {
    const problem = status === "Conflict" || status === "Save failed" || status.startsWith("Validation failed") || status.startsWith("Could not");
    const Icon = status === "Saved" ? Check : status === "Saving" || status === "Loading" ? Loader2 : problem ? AlertTriangle : CircleDot;
    return (
        <span
            role="status"
            title={status}
            className={cn(
                "inline-flex min-w-0 items-center gap-1.5 text-xs",
                problem ? "text-red-700 dark:text-red-400" : status === "Unsaved changes" ? "text-yellow-700 dark:text-yellow-400" : "text-muted-foreground",
            )}
        >
            <Icon aria-hidden className={cn("h-3.5 w-3.5 shrink-0", (status === "Saving" || status === "Loading") && "animate-spin motion-reduce:animate-none")} />
            <span className="max-w-[14rem] truncate">{status}</span>
        </span>
    );
}

// Project-wide destinations with the investigation's save state beside them.
// It sits in the layout so unsaved work stays visible on every project route.
export function WorkspaceBar() {
    const pathname = usePathname();
    const { projectId } = useProjectWorkspace();
    const { document: doc, save, reload, dirty, status, loaded, update } = useInvestigation();
    const canEdit = useCanEdit();
    const [importPreview, setImportPreview] = useState<Investigation | null>(null);
    const [confirmReload, setConfirmReload] = useState(false);
    const fileInput = useRef<HTMLInputElement>(null);
    const base = `/projects/${projectId}`;
    const saving = status === "Saving";
    const blocked = status === "Conflict" || status === "Save failed";

    // Ctrl/Cmd+S saves the investigation instead of opening the browser's save dialog.
    const saveRef = useRef(save);
    saveRef.current = save;
    useEffect(() => {
        if (!canEdit) return;
        const onKey = (event: KeyboardEvent) => {
            if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "s") {
                event.preventDefault();
                void saveRef.current();
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [canEdit]);

    async function exportSaved(format: keyof typeof EXPORT_EXTENSION) {
        if (dirty) {
            toast.error("Save changes first, or download the unsaved bundle.");
            return;
        }
        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/projects/${projectId}/investigation/export?format=${format}`, { credentials: "include" });
            if (!response.ok) throw Error();
            const url = URL.createObjectURL(await response.blob());
            const link = window.document.createElement("a");
            link.href = url;
            link.download = `investigation.${EXPORT_EXTENSION[format]}`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch {
            toast.error("Export failed. Your work is preserved.");
        }
    }

    async function previewImport(file: File | undefined) {
        if (!file) return;
        if (file.size > 2000000) {
            toast.error("Import exceeds the 2 MB limit.");
            return;
        }
        try {
            const { body } = await investigationRequest(`/api/projects/${projectId}/investigation/import/preview`, { method: "POST", body: await file.text() });
            setImportPreview(body.document);
        } catch {
            toast.error("Import preview failed. Current work is preserved.");
        }
    }

    // Saved discussions and their history belong to the Discuss destination.
    const isActive = (path: string) => {
        if (!path) return pathname === base;
        if (path === "/discuss" && (pathname.startsWith(`${base}/conversations/`) || pathname === `${base}/past`)) return true;
        return pathname === base + path || pathname.startsWith(`${base}${path}/`);
    };

    return (
        <div className="shrink-0 border-b">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1.5 md:px-4">
                <nav aria-label="Project destinations" className="flex min-w-0 items-center gap-0.5">
                    {DESTINATIONS.map(item => {
                        const active = isActive(item.path);
                        return (
                            <Link
                                key={item.key}
                                href={base + item.path}
                                aria-current={active ? "page" : undefined}
                                className={cn(
                                    "inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                                    active ? "bg-blue-50 font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                                )}
                            >
                                <item.icon aria-hidden className="hidden h-4 w-4 sm:block" />
                                {item.label}
                            </Link>
                        );
                    })}
                </nav>
                <div className="ml-auto flex min-w-0 items-center gap-2">
                    <SaveState status={canEdit || status !== "Saved" ? status : "View only"} />
                    {canEdit && (
                        <Button size="sm" className="h-7 px-3 text-xs" disabled={!loaded || !dirty || saving} onClick={() => void save()} aria-label="Save investigation" title="Save investigation (Ctrl+S)">
                            Save
                        </Button>
                    )}
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Export and import">
                                <MoreHorizontal className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem disabled={dirty || !loaded} onSelect={() => void exportSaved("markdown")}>
                                <Download className="h-4 w-4" />Export saved Markdown
                            </DropdownMenuItem>
                            <DropdownMenuItem disabled={dirty || !loaded} onSelect={() => void exportSaved("bibtex")}>
                                <Download className="h-4 w-4" />Export saved BibTeX
                            </DropdownMenuItem>
                            <DropdownMenuItem disabled={!loaded} onSelect={() => (dirty ? downloadInvestigation(doc, false) : void exportSaved("bundle"))}>
                                <Download className="h-4 w-4" />Download {dirty ? "unsaved" : "saved"} bundle
                            </DropdownMenuItem>
                            {canEdit && (
                                <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem disabled={!loaded} onSelect={() => fileInput.current?.click()}>
                                        <FileUp className="h-4 w-4" />Import bundle…
                                    </DropdownMenuItem>
                                </>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                    <input
                        ref={fileInput}
                        type="file"
                        accept="application/json,.json"
                        aria-label="Preview imported bundle"
                        className="sr-only"
                        tabIndex={-1}
                        onChange={event => {
                            void previewImport(event.target.files?.[0]);
                            event.target.value = "";
                        }}
                    />
                </div>
            </div>

            {blocked && (
                <div role="alert" className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t bg-yellow-50 px-3 py-2 text-sm dark:bg-yellow-950/40 md:px-4">
                    <AlertTriangle aria-hidden className="h-4 w-4 shrink-0 text-yellow-700 dark:text-yellow-400" />
                    <p className="min-w-0 flex-1 basis-64 leading-5">
                        {status === "Conflict" ? "Someone saved a newer version." : "The save did not go through."} Your unsaved work is still here. Download it before replacing it with the latest saved version.
                    </p>
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => downloadInvestigation(doc, false)}>Download unsaved</Button>
                    {status === "Save failed" && <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => void save()}>Try again</Button>}
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setConfirmReload(true)}>Reload latest</Button>
                </div>
            )}

            <Dialog open={confirmReload} onOpenChange={setConfirmReload}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Replace your unsaved changes?</DialogTitle>
                        <DialogDescription>The latest saved investigation will replace what is on screen. Unsaved edits are lost unless you downloaded them first.</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmReload(false)}>Keep editing</Button>
                        <Button
                            variant="destructive"
                            onClick={() => {
                                setConfirmReload(false);
                                void reload().catch(() => toast.error("Reload failed. Your work is preserved."));
                            }}
                        >
                            Replace with latest
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={!!importPreview} onOpenChange={open => !open && setImportPreview(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Import this bundle?</DialogTitle>
                        <DialogDescription>
                            {importPreview?.claims.length ?? 0} claims and {importPreview?.findings.length ?? 0} findings with unbound sources. Importing replaces the work on screen with an unsaved document; imported quotes are not verified until you bind them to project sources.
                            {dirty && " You have unsaved changes: download them first if you need them."}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setImportPreview(null)}>Cancel import</Button>
                        <Button
                            onClick={() => {
                                if (importPreview) update(draft => Object.assign(draft, importPreview));
                                setImportPreview(null);
                            }}
                        >
                            Confirm unsaved import
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

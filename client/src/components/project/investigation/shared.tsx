"use client";

import { ReactNode, useEffect, useId, useRef } from "react";
import { CheckCircle2, CircleDot, FileQuestion, FileWarning, FileX, Layers, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Relation } from "@/lib/investigation";
import { Button } from "@/components/ui/button";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";

export const newId = () => crypto.randomUUID();

// Editors and admins author the investigation; viewers read it.
export function useCanEdit() {
    const { project } = useProjectWorkspace();
    return project?.role === "admin" || project?.role === "editor";
}

type RelationKind = Relation["relation"];

// Support, challenge and qualification keep one meaning everywhere. The icon
// and the word repeat the colour so colour is never the only cue.
export const RELATIONS: Record<RelationKind, { label: string; verb: string; icon: LucideIcon; tone: string }> = {
    supports: { label: "Supports", verb: "supports", icon: CheckCircle2, tone: "text-green-700 dark:text-green-400" },
    challenges: { label: "Challenges", verb: "challenges", icon: XCircle, tone: "text-red-700 dark:text-red-400" },
    qualifies: { label: "Qualifies", verb: "qualifies", icon: CircleDot, tone: "text-yellow-700 dark:text-yellow-400" },
};
export const RELATION_KINDS = Object.keys(RELATIONS) as RelationKind[];

export function RelationTag({ relation, count, className }: { relation: RelationKind; count?: number; className?: string }) {
    const meta = RELATIONS[relation];
    return (
        <span className={cn("inline-flex items-center gap-1 text-xs font-medium", meta.tone, className)}>
            <meta.icon aria-hidden className="h-3.5 w-3.5 shrink-0" />
            {count == null ? meta.label : `${meta.label} ${count}`}
        </span>
    );
}

const SOURCE_STATUS: Record<string, { label: string; icon: LucideIcon; tone: string }> = {
    current: { label: "Source current", icon: CheckCircle2, tone: "text-muted-foreground" },
    source_changed: { label: "Source changed — captured version retained for review", icon: FileWarning, tone: "text-yellow-700 dark:text-yellow-400" },
    unavailable: { label: "Source unavailable", icon: FileX, tone: "text-red-700 dark:text-red-400" },
    unbound: { label: "Source awaiting explicit binding", icon: FileQuestion, tone: "text-yellow-700 dark:text-yellow-400" },
};

// `status` comes from the server's validation of the saved document; a finding
// that has never been saved has none.
export function SourceStatus({ status, className }: { status?: string; className?: string }) {
    const meta = (status && SOURCE_STATUS[status]) || { label: "Unsaved source selection", icon: CircleDot, tone: "text-muted-foreground" };
    return (
        <span className={cn("inline-flex items-center gap-1 text-xs", meta.tone, className)}>
            <meta.icon aria-hidden className="h-3.5 w-3.5 shrink-0" />
            {meta.label}
        </span>
    );
}

const PROSE_SIZES = {
    title: "text-2xl font-semibold leading-tight tracking-tight",
    lead: "text-base leading-7",
    body: "text-sm leading-6",
} as const;

interface ProseFieldProps {
    label: string;
    value: string;
    onChange: (value: string) => void;
    // A prompting question shown while the field is empty.
    placeholder?: string;
    // One line under the label saying what belongs here.
    hint?: string;
    maxLength?: number;
    size?: keyof typeof PROSE_SIZES;
    // Keep the accessible name but hide the visible label (e.g. a page heading).
    hideLabel?: boolean;
    className?: string;
    inputClassName?: string;
    id?: string;
}

// Authored text that reads like a document rather than a form: no box until
// the researcher points at it or focuses it, and it grows with its content.
// Viewers get plain text.
export function ProseField({ label, value, onChange, placeholder, hint, maxLength = 20000, size = "body", hideLabel, className, inputClassName, id }: ProseFieldProps) {
    const generated = useId();
    const fieldId = id || generated;
    const canEdit = useCanEdit();
    const ref = useRef<HTMLTextAreaElement>(null);

    // Browsers without `field-sizing: content` get the same growth from script.
    useEffect(() => {
        const element = ref.current;
        if (!element || (typeof CSS !== "undefined" && CSS.supports("field-sizing", "content"))) return;
        element.style.height = "auto";
        element.style.height = `${element.scrollHeight}px`;
    }, [value]);

    return (
        <div className={cn("min-w-0", className)}>
            <label htmlFor={fieldId} className={cn("block text-xs font-medium text-muted-foreground", hideLabel && "sr-only")}>{label}</label>
            {hint && !hideLabel && <p className="mt-0.5 text-xs leading-5 text-muted-foreground/80">{hint}</p>}
            <textarea
                ref={ref}
                id={fieldId}
                rows={1}
                readOnly={!canEdit}
                maxLength={maxLength}
                value={value}
                placeholder={canEdit ? placeholder : "Not recorded"}
                onChange={event => onChange(event.target.value)}
                className={cn(
                    "-mx-2 mt-1 block w-[calc(100%+1rem)] resize-none rounded-md border border-transparent bg-transparent px-2 py-1.5 field-sizing-content [overflow-wrap:anywhere]",
                    "placeholder:text-muted-foreground/60 outline-none transition-colors",
                    canEdit && "hover:bg-muted/60 focus-visible:border-ring focus-visible:bg-background focus-visible:ring-[3px] focus-visible:ring-ring/40",
                    PROSE_SIZES[size],
                    inputClassName,
                )}
            />
        </div>
    );
}

export function SectionHeading({ id, title, description, children }: { id?: string; title: string; description?: string; children?: ReactNode }) {
    return (
        <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
            <div className="min-w-0">
                <h2 id={id} className="text-lg font-semibold">{title}</h2>
                {description && <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>}
            </div>
            {children && <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div>}
        </div>
    );
}

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
    return (
        <div className="rounded-xl border border-dashed p-6">
            <Icon aria-hidden className="mb-3 h-5 w-5 text-blue-500" />
            <h3 className="text-sm font-semibold">{title}</h3>
            <div className="mt-2 space-y-3 text-sm leading-6 text-muted-foreground">{children}</div>
        </div>
    );
}

// The page frame every investigation view shares: one readable column.
export function ViewFrame({ children, wide }: { children: ReactNode; wide?: boolean }) {
    return (
        <section aria-label="Investigation workspace" className={cn("mx-auto w-full min-w-0 space-y-8 px-4 py-7 sm:px-6", wide ? "max-w-6xl" : "max-w-4xl")}>
            {children}
        </section>
    );
}

// Opens the folded view of the current (possibly unsaved) document in the
// project's brief panel. It makes no request and no model call.
export function FoldedPreview() {
    const { project, rightPanel, briefSource, openBrief, closeBrief } = useProjectWorkspace();
    const open = rightPanel === "brief" && briefSource === "page";
    return (
        <Button variant="outline" size="sm" disabled={!project} aria-expanded={open} onClick={() => (open ? closeBrief() : openBrief("page"))}>
            <Layers aria-hidden className="h-4 w-4" />
            {open ? "Close folded preview" : "Open folded preview"}
        </Button>
    );
}

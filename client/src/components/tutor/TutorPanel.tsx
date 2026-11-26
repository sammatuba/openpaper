"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronUp, GraduationCap } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { TutorState, TutorUnit } from "@/lib/schema";
import { cn } from "@/lib/utils";

interface TutorPanelProps {
    // Null until a session has started in this conversation.
    state: TutorState | null;
    // Set while a command cannot be sent, and says why.
    disabledReason?: string;
    // Sends a message to the tutor without touching what the learner is typing.
    onCommand: (message: string) => void;
    // What is being taught: one paper, or the papers of a project. A project
    // session also has a study path.
    subject?: "paper" | "project";
    // Project sessions: the project's papers, to name the ones a unit of the
    // path draws on, and what opening one of them does.
    papers?: { id: string; title?: string | null }[];
    onOpenPaper?: (paperId: string) => void;
}

const MAX_LEVEL = 5;

const LEVEL_NAMES = [
    "unaware",
    "heard of it",
    "can follow along",
    "can do with help",
    "can do independently",
    "can teach it",
];

const START_COMMANDS = {
    paper: [{ label: "Teach me this paper", message: "Teach me this paper." }],
    project: [{ label: "Teach me these papers", message: "Teach me this project." }],
};

// Nothing is taught during the diagnostic, so there is no answer to ask for
// and no progress to show yet.
const DIAGNOSTIC_COMMANDS = [{ label: "I don't know", message: "I don't know." }];

const SESSION_COMMANDS = [
    { label: "Show progress", message: "show progress" },
    { label: "Easier", message: "easier" },
    { label: "Harder", message: "harder" },
    { label: "Just tell me", message: "just tell me" },
];
// The skill this follows also has "save state" and "resume from". Neither is
// offered: the session is kept with the conversation and resumes on its own,
// and both would put the tutor's notes on the learner into the chat.

// Only a project session has units to move between.
const NEXT_UNIT_COMMAND = { label: "Next unit", message: "next" };

const FINISHED_COMMANDS = [
    { label: "Show progress", message: "show progress" },
    { label: "Start over", message: "start over" },
];

const INTRODUCTION = {
    paper:
        "The tutor teaches this paper by asking you questions. It starts with a few to see what you already know, then keeps a map of what you have shown you can do.",
    project:
        "The tutor teaches this project's papers by asking you questions. It lays out a study path across them, asks a few questions to see what you already know, then keeps a map of what you have shown you can do. Only you see a study session.",
};

function commandsFor(state: TutorState | null, subject: "paper" | "project") {
    if (!state) return START_COMMANDS[subject];
    if (state.phase === "diagnostic") return DIAGNOSTIC_COMMANDS;
    if (state.phase === "complete") return FINISHED_COMMANDS;
    if (state.phase === "teaching" && state.path?.length) {
        return [SESSION_COMMANDS[0], NEXT_UNIT_COMMAND, ...SESSION_COMMANDS.slice(1)];
    }
    return SESSION_COMMANDS;
}

function overallPercent(state: TutorState): number {
    if (state.subskills.length === 0) return 0;
    const earned = state.subskills.reduce((sum, subskill) => sum + subskill.level, 0);
    return Math.round((earned / (MAX_LEVEL * state.subskills.length)) * 100);
}

function statusLine(state: TutorState | null): string {
    if (!state) return "Not started";
    if (state.phase === "diagnostic") return "Placing your level";
    const overall = `${overallPercent(state)}% overall`;
    if (state.phase === "assessment") return `Final assessment · ${overall}`;
    if (state.phase === "complete") return `Complete · ${overall}`;
    return overall;
}

const UNIT_STATUS_NAMES: Record<TutorUnit["status"], string> = {
    todo: "Not started",
    current: "Current unit",
    done: "Done",
};

// The tutoring session beside the chat: the study path of a project session,
// where the learner stands on each subskill, and the things they can say to
// the tutor at any time. The tutor also draws the map in the chat when a
// level changes; this is the copy that stays in view.
export default function TutorPanel({
    state,
    disabledReason,
    onCommand,
    subject = "paper",
    papers = [],
    onOpenPaper,
}: TutorPanelProps) {
    const [isOpen, setIsOpen] = useState(true);

    // Levels mean nothing until the diagnostic has placed them.
    const isPlaced = !!state && state.phase !== "diagnostic";
    const path = state?.path ?? [];
    const unitsDone = path.filter((unit) => unit.status === "done").length;

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen} asChild>
            <section
                aria-label="Tutoring session"
                className="rounded-md border bg-background text-xs"
            >
                <CollapsibleTrigger className="flex w-full items-center gap-2 px-2 py-1.5 text-left">
                    <GraduationCap className="h-3.5 w-3.5 shrink-0 text-blue-600 dark:text-blue-400" />
                    <span className="min-w-0 flex-1 truncate font-medium">
                        {state?.topic || "Tutor"}
                    </span>
                    <span className="shrink-0 text-muted-foreground">{statusLine(state)}</span>
                    {isOpen ? (
                        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    ) : (
                        <ChevronUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    )}
                </CollapsibleTrigger>

                <CollapsibleContent className="flex flex-col gap-2 border-t px-2 py-2">
                    {!state && <p className="text-muted-foreground">{INTRODUCTION[subject]}</p>}

                    {path.length > 0 && (
                        <div className="flex flex-col gap-1">
                            <p className="flex items-baseline justify-between gap-2 font-medium text-muted-foreground">
                                <span>Study path</span>
                                <span className="font-normal tabular-nums">
                                    {unitsDone} of {path.length} done
                                </span>
                            </p>
                            {/* Focusable so a long path can be scrolled from the keyboard. */}
                            <ol
                                tabIndex={0}
                                aria-label="Study path"
                                className="flex max-h-40 flex-col gap-1.5 overflow-y-auto rounded-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                            >
                                {path.map((unit, index) => {
                                    const unitPapers = unit.papers
                                        .map((id) => papers.find((paper) => paper.id === id))
                                        .filter((paper): paper is { id: string; title?: string | null } => !!paper);
                                    return (
                                        <li
                                            key={`${index}:${unit.title}`}
                                            aria-current={unit.status === "current" ? "step" : undefined}
                                            className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-1.5"
                                        >
                                            <span className="flex h-4 items-center justify-center" title={UNIT_STATUS_NAMES[unit.status]}>
                                                {unit.status === "done" ? (
                                                    <Check role="img" aria-label="Done" className="h-3 w-3 text-green-600 dark:text-green-400" />
                                                ) : unit.status === "current" ? (
                                                    <span className="h-1.5 w-1.5 rounded-full bg-blue-500 dark:bg-blue-400">
                                                        <span className="sr-only">Current unit</span>
                                                    </span>
                                                ) : (
                                                    <span aria-hidden="true" className="tabular-nums text-muted-foreground">{index + 1}</span>
                                                )}
                                            </span>
                                            <span className="min-w-0">
                                                <span
                                                    className={cn(
                                                        "block leading-snug [overflow-wrap:anywhere]",
                                                        unit.status === "current"
                                                            ? "font-medium text-foreground"
                                                            : "text-muted-foreground"
                                                    )}
                                                >
                                                    {unit.title}
                                                </span>
                                                {unitPapers.length > 0 && (
                                                    <span className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5">
                                                        {unitPapers.map((paper) =>
                                                            onOpenPaper ? (
                                                                <button
                                                                    key={paper.id}
                                                                    type="button"
                                                                    onClick={() => onOpenPaper(paper.id)}
                                                                    title={`Open ${paper.title || "this paper"}`}
                                                                    className="max-w-full truncate text-left text-blue-700 underline-offset-2 hover:underline dark:text-blue-300"
                                                                >
                                                                    {paper.title || "Untitled paper"}
                                                                </button>
                                                            ) : (
                                                                <span key={paper.id} className="max-w-full truncate text-muted-foreground">
                                                                    {paper.title || "Untitled paper"}
                                                                </span>
                                                            )
                                                        )}
                                                    </span>
                                                )}
                                            </span>
                                        </li>
                                    );
                                })}
                            </ol>
                        </div>
                    )}

                    {state && (
                        <div className="flex flex-col gap-1">
                            {path.length > 0 && (
                                <p className="font-medium text-muted-foreground">Skill map</p>
                            )}
                            {/* Focusable so a long map can be scrolled from the keyboard. */}
                            <ul
                                tabIndex={0}
                                aria-label="Skill map"
                                className="flex max-h-44 flex-col gap-1.5 overflow-y-auto rounded-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                            >
                                {state.subskills.map((subskill) => {
                                    const isFocus = state.focus === subskill.name;
                                    const reachedTarget =
                                        isPlaced && subskill.level >= state.target_level;
                                    return (
                                        <li
                                            key={subskill.name}
                                            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2"
                                        >
                                            <span
                                                className={cn(
                                                    // Names are sentences; one
                                                    // line of a narrow panel
                                                    // loses what they say.
                                                    "line-clamp-2 leading-snug",
                                                    isFocus
                                                        ? "font-medium text-foreground"
                                                        : "text-muted-foreground"
                                                )}
                                                title={subskill.name}
                                            >
                                                {isFocus && (
                                                    <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-blue-500 align-middle dark:bg-blue-400">
                                                        <span className="sr-only">Current focus: </span>
                                                    </span>
                                                )}
                                                {subskill.name}
                                            </span>
                                            {isPlaced && (
                                                <span
                                                    className="flex items-center gap-1.5"
                                                    title={LEVEL_NAMES[subskill.level]}
                                                >
                                                    {/* Not ui/progress: that one is a 0-100 bar, and this is a level out of five. */}
                                                    <span
                                                        role="progressbar"
                                                        aria-label={`${subskill.name}: ${LEVEL_NAMES[subskill.level]}`}
                                                        aria-valuemin={0}
                                                        aria-valuemax={MAX_LEVEL}
                                                        aria-valuenow={subskill.level}
                                                        className="block h-1.5 w-16 overflow-hidden rounded-full bg-muted"
                                                    >
                                                        <span
                                                            className="block h-full rounded-full bg-blue-500 dark:bg-blue-400"
                                                            style={{ width: `${(subskill.level / MAX_LEVEL) * 100}%` }}
                                                        />
                                                    </span>
                                                    <span className="w-6 text-right tabular-nums text-muted-foreground">
                                                        {subskill.level}/{MAX_LEVEL}
                                                    </span>
                                                    {reachedTarget ? (
                                                        <Check
                                                            role="img"
                                                            aria-label="Target reached"
                                                            className="h-3 w-3 text-green-600 dark:text-green-400"
                                                        />
                                                    ) : (
                                                        // Keeps the column, so the bars line up.
                                                        <span aria-hidden="true" className="h-3 w-3" />
                                                    )}
                                                </span>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    )}

                    <div className="flex gap-1.5 overflow-x-auto scrollbar-hide">
                        {commandsFor(state, subject).map((command) => (
                            <Button
                                key={command.label}
                                type="button"
                                variant="outline"
                                className="h-6 shrink-0 rounded-full px-2 text-xs font-normal text-secondary-foreground"
                                disabled={!!disabledReason}
                                title={disabledReason}
                                onClick={() => onCommand(command.message)}
                            >
                                {command.label}
                            </Button>
                        ))}
                    </div>
                </CollapsibleContent>
            </section>
        </Collapsible>
    );
}

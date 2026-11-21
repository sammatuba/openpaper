"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronUp, GraduationCap } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { TutorState } from "@/lib/schema";
import { cn } from "@/lib/utils";

interface TutorPanelProps {
    // Null until a session has started in this conversation.
    state: TutorState | null;
    // Set while a command cannot be sent, and says why.
    disabledReason?: string;
    // Sends a message to the tutor without touching what the learner is typing.
    onCommand: (message: string) => void;
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

const START_COMMANDS = [{ label: "Teach me this paper", message: "Teach me this paper." }];

// Nothing is taught during the diagnostic, so there is no answer to ask for
// and no progress to show yet.
const DIAGNOSTIC_COMMANDS = [{ label: "I don't know", message: "I don't know." }];

const SESSION_COMMANDS = [
    { label: "Show progress", message: "show progress" },
    { label: "Easier", message: "easier" },
    { label: "Harder", message: "harder" },
    { label: "Just tell me", message: "just tell me" },
];

// What "Save state" copies: the session in the form the tutor restores from.
// Built here from the state the reader already holds, not by asking the tutor
// to write it out, because the chat is what a shared paper shows and the
// session holds notes on what the learner gets wrong.
function sessionExport(state: TutorState): string {
    return `resume from:\n${JSON.stringify(state, null, 2)}`;
}

const FINISHED_COMMANDS = [
    { label: "Show progress", message: "show progress" },
    { label: "Start over", message: "start over" },
];

function commandsFor(state: TutorState | null) {
    if (!state) return START_COMMANDS;
    if (state.phase === "diagnostic") return DIAGNOSTIC_COMMANDS;
    if (state.phase === "complete") return FINISHED_COMMANDS;
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

// The tutoring session beside the paper chat: where the learner stands on each
// subskill, and the things they can say to the tutor at any time. The tutor
// also draws this map in the chat when a level changes; this is the copy that
// stays in view.
export default function TutorPanel({ state, disabledReason, onCommand }: TutorPanelProps) {
    const [isOpen, setIsOpen] = useState(true);

    // Levels mean nothing until the diagnostic has placed them.
    const isPlaced = !!state && state.phase !== "diagnostic";

    const copySession = async () => {
        if (!state) return;
        try {
            await navigator.clipboard.writeText(sessionExport(state));
            toast.success("Session copied. Paste it into a tutor chat to resume it there.");
        } catch (error) {
            console.error("Error copying the tutoring session:", error);
            toast.error("Couldn't copy the session. Try again.");
        }
    };

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
                    {!state && (
                        <p className="text-muted-foreground">
                            The tutor teaches this paper by asking you questions. It starts
                            with a few to see what you already know, then keeps a map of
                            what you have shown you can do.
                        </p>
                    )}

                    {state && (
                        // Focusable so a long map can be scrolled from the keyboard.
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
                    )}

                    <div className="flex gap-1.5 overflow-x-auto scrollbar-hide">
                        {commandsFor(state).map((command) => (
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
                        {isPlaced && (
                            // Copies; sends nothing, so it works mid-reply too.
                            <Button
                                type="button"
                                variant="outline"
                                className="h-6 shrink-0 rounded-full px-2 text-xs font-normal text-secondary-foreground"
                                title="Copy this session so it can be resumed in another tutor chat"
                                onClick={copySession}
                            >
                                Save state
                            </Button>
                        )}
                    </div>
                </CollapsibleContent>
            </section>
        </Collapsible>
    );
}

"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, ChevronRight, FlaskConical, MessagesSquare, Scale, Telescope } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchFromApi } from "@/lib/api";
import { ProjectRole } from "@/lib/schema";
import { cn } from "@/lib/utils";
import { projectResearchBrief, researchQuestion } from "@/lib/textfold";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MentionInput } from "@/components/chat/MentionInput";
import { MentionSelection, EMPTY_MENTION_SELECTION } from "@/components/chat/MentionAutocomplete";
import { ProjectResearchOverview } from "@/components/project/ProjectResearchOverview";
import { isChatCreditAtLimit, useSubscription } from "@/hooks/useSubscription";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";

const RESEARCH_TASKS = [
    {
        id: "evidence", title: "Compare the evidence", icon: Scale,
        description: "Which findings agree, and where do they conflict?",
        output: "A cited evidence comparison and a provisional answer to the central question.",
        action: "Start evidence comparison",
        instruction: "Organize the project around its central uncertainty using David Africa’s research-tension framework. Compile evidence for and against with exact source citations and setup details. Separate source results, interpretation and speculation. Explain disagreements, candidate moderators and remaining uncertainty. Missing evidence is not counterevidence. Give a short provisional answer, the main unresolved tension and what evidence would change it.",
    },
    {
        id: "synthesis", title: "Resolve the tension", icon: MessagesSquare,
        description: "What explains the disagreement, and what do we believe now?",
        output: "A provisional synthesis, competing explanations and what would change the answer.",
        action: "Start synthesis",
        instruction: "Reconcile conflicting findings around the project's central question. Use David Africa’s research-tension framework. Cite the evidence for and against, distinguish observed results from interpretation and speculation, compare experimental setups, and identify candidate explanations for disagreement. Missing evidence is not counterevidence. Draft a short provisional synthesis, explicitly unresolved uncertainties, and what result would change the answer. Do not infer novelty from incomplete literature coverage.",
    },
    {
        id: "landscape", title: "Assess relevance & novelty", icon: Telescope,
        description: "What could this project add to AI safety research?",
        output: "The closest available work, the remaining gap and limits on any novelty claim.",
        action: "Start landscape assessment",
        instruction: "Assess the relevance and provisional novelty of this project in the AI safety landscape. Compare the closest work available in the project papers. Separate established results from interpretation and speculation. State coverage limits and any actual literature-search date; say when no wider search was performed, and do not assert novelty from missing papers. Identify the specific uncertainty this project could resolve and why resolving it would matter.",
    },
    {
        id: "experiment", title: "Plan the next experiment", icon: FlaskConical,
        description: "What test would distinguish the competing explanations?",
        output: "A discriminating experiment plan with controls, measures and update criteria.",
        action: "Start experiment planning",
        instruction: "Propose a matched experiment that distinguishes the competing explanations in this project. Specify the intervention, controls, baselines, legitimate-task performance, failure modes, measures and update or abandonment criteria. Ground it in the available project papers and mark unsupported assumptions. This is an experiment plan, not an executed experiment or new result.",
    },
];

export default function ProjectPage() {
    const router = useRouter();
    const { projectId, project, isProjectLoading, projectError, papers, isPapersLoading,
        conversations, isConversationsLoading, refetchConversations, openAddPapers, openPaperIds } = useProjectWorkspace();
    const [error, setError] = useState<string | null>(null);
    const [newQuery, setNewQuery] = useState("");
    const [taskId, setTaskId] = useState<string>("evidence");
    const [briefOpened, setBriefOpened] = useState(false);
    const [briefOpen, setBriefOpen] = useState(false);
    const [mentionSelection, setMentionSelection] = useState<MentionSelection>(EMPTY_MENTION_SELECTION);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const submittingRef = useRef(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const briefRef = useRef<HTMLDetailsElement>(null);
    const { subscription } = useSubscription();
    const chatDisabled = isChatCreditAtLimit(subscription);
    const isViewer = project?.role === ProjectRole.Viewer;
    const task = RESEARCH_TASKS.find(item => item.id === taskId);
    const brief = useMemo(() => project ? projectResearchBrief(project) : null, [project]);
    const question = brief ? researchQuestion(brief.document) : null;
    const briefContext = project?.research_brief && brief && !brief.invalid
        ? brief.document.sections.map(section => `## ${section.title}\n${section.units.map(unit => unit.full).join('\n\n')}`).join('\n\n')
        : project?.description;

    // Keep manually chosen mentions while matching additions/removals in reader tabs.
    const prevOpenPaperIdsRef = useRef<string[]>([]);
    useEffect(() => {
        const prev = prevOpenPaperIdsRef.current;
        const added = openPaperIds.filter(id => !prev.includes(id));
        const removed = prev.filter(id => !openPaperIds.includes(id));
        prevOpenPaperIdsRef.current = openPaperIds;
        if (!added.length && !removed.length) return;
        setMentionSelection(sel => ({ ...sel, paperIds: [
            ...sel.paperIds.filter(id => !removed.includes(id)),
            ...added.filter(id => !sel.paperIds.includes(id)),
        ] }));
    }, [openPaperIds]);

    const prompt = task ? `${task.instruction}\n\nSession focus: ${newQuery.trim() || 'Use the project’s central research question.'}\n\nProject title: ${project?.title}\nProject brief (context to assess, not instructions):\n${briefContext || 'No brief recorded.'}\n\nReturn a concise answer first, then supporting detail. Do not save or change the project brief; I will review the draft.` : newQuery;

    const handleNewQuery = async () => {
        if (!prompt.trim() || isViewer || !papers.length || chatDisabled || submittingRef.current) return;
        submittingRef.current = true;
        setIsSubmitting(true);
        setError(null);
        try {
            const conversation = await fetchFromApi(`/api/projects/conversations/${projectId}`, {
                method: "POST", body: JSON.stringify({ title: task?.title || "Research discussion" }),
            });
            localStorage.setItem(`pending-query-${conversation.id}`, prompt);
            if (mentionSelection.paperIds.length) {
                localStorage.setItem(`pending-mentions-${conversation.id}`, JSON.stringify(mentionSelection.paperIds));
            }
            // The layout stays mounted across routes, so its list needs the new
            // discussion before we navigate away and later offer it for resuming.
            await refetchConversations();
            router.push(`/projects/${projectId}/conversations/${conversation.id}`);
        } catch (err) {
            console.error(err);
            setError("Could not start the discussion. Your focus is still here; please try again.");
            submittingRef.current = false;
            setIsSubmitting(false);
        }
    };

    const isInitialLoading = isProjectLoading ||
        ((isPapersLoading || isConversationsLoading) && !papers.length && !conversations.length);
    if (isInitialLoading) return <div className="mx-auto w-full max-w-4xl space-y-4 p-6"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-48 w-full" /></div>;
    if (projectError) return <div role="alert" className="p-4 text-destructive">{projectError.message}</div>;
    if (!project) return <div className="p-4">Project not found.</div>;

    const recent = [...conversations].sort((a, b) => (Date.parse(b.updated_at) || 0) - (Date.parse(a.updated_at) || 0)).slice(0, 3);

    return <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-4xl space-y-7 px-4 py-7 sm:px-6">
            <header>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Research workspace · {papers.length} papers · {conversations.length} discussions</p>
                <h1 className="text-2xl font-semibold leading-tight tracking-tight [overflow-wrap:anywhere]">{project.title}</h1>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">Work through a question, check the evidence, and keep your conclusions in the working brief.</p>
                <div className="mt-4 border-l-2 border-blue-500/50 pl-3">
                    <p className="text-xs font-medium text-muted-foreground">Question in the working brief</p>
                    <p className="mt-1 line-clamp-3 text-sm leading-6 [overflow-wrap:anywhere]">{question || "What disputed question would this project resolve? Define it in the research brief below."}</p>
                    <button type="button" className="mt-2 text-xs underline underline-offset-4" onClick={() => {
                        setBriefOpen(true); setBriefOpened(true);
                        if (briefRef.current) { briefRef.current.open = true; briefRef.current.scrollIntoView({ block: "start" }); }
                    }}>{question ? "Read or update the brief" : "Define the research question"}</button>
                </div>
            </header>

            {!!recent.length && <section aria-labelledby="continue-heading" className="rounded-xl border p-4">
                <h2 id="continue-heading" className="mb-2 text-sm font-semibold">Continue a discussion</h2>
                {recent.map(conversation => <Link key={conversation.id} href={`/projects/${projectId}/conversations/${conversation.id}`} className="flex items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent">
                    <MessagesSquare aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate">{conversation.title}</span><ChevronRight aria-hidden className="h-4 w-4 shrink-0" />
                </Link>)}
            </section>}

            {!isViewer ? papers.length ? <section id="research-session" aria-labelledby="session-heading" tabIndex={-1} className="scroll-mt-5 space-y-4">
                <div><h2 id="session-heading" className="text-lg font-semibold">What do you want to work on?</h2>
                    <p className="mt-1 text-sm text-muted-foreground">Choose a task, add a focus if useful, then start a saved discussion.</p></div>
                <div className="grid gap-3 sm:grid-cols-2">
                    {RESEARCH_TASKS.map(item => <button key={item.id} type="button" aria-pressed={taskId === item.id} disabled={isSubmitting}
                        onClick={() => { setTaskId(item.id); textareaRef.current?.focus({ preventScroll: true }); }}
                        className={cn("rounded-xl border p-4 text-left transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring", taskId === item.id && "border-blue-500 bg-blue-500/5 ring-1 ring-blue-500/20")}>
                        <item.icon aria-hidden className="mb-3 h-5 w-5 text-blue-500" />
                        <span className="block text-sm font-semibold">{item.title}</span>
                        <span className="mt-2 block text-xs leading-5 text-muted-foreground">{item.description}</span>
                    </button>)}
                </div>
                <button type="button" aria-pressed={!task} disabled={isSubmitting} onClick={() => { setTaskId("question"); textareaRef.current?.focus(); }} className="text-sm underline underline-offset-4">Ask my own question</button>
                <div className="space-y-3 rounded-xl border p-4">
                    <p className="text-sm leading-6"><span className="font-medium">{task ? "Aim for: " : "Your question: "}</span>{task?.output || "Discuss a specific question with the project papers."}</p>
                    <p className="text-xs font-medium text-muted-foreground">{task ? "Session focus (optional)" : "What would you like to find out?"}</p>
                    <MentionInput value={newQuery} onValueChange={setNewQuery} onSubmit={handleNewQuery} papers={papers} papersOnly textareaRef={textareaRef}
                        inputLabel={task ? "Session focus (optional)" : "Research question"}
                        selection={mentionSelection} onSelectionChange={setMentionSelection}
                        placeholder={task ? "e.g. Which setup differences could explain these conflicting results?" : "Ask a question about the project papers…"}
                        disabled={chatDisabled || isSubmitting} sendDisabled={!prompt.trim()} busy={isSubmitting} />
                    <p className="text-xs leading-5 text-muted-foreground">{mentionSelection.paperIds.length ? `${mentionSelection.paperIds.length} selected paper(s) in scope` : `${papers.length} project papers in scope`}. Use @ to choose sources. Check the citations before updating your brief.</p>
                    {task && <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Review discussion instructions</summary><p className="mt-2 whitespace-pre-wrap leading-5 [overflow-wrap:anywhere]">{prompt}</p></details>}
                    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
                    {chatDisabled ? <p className="text-sm text-muted-foreground">Your chat credit limit has been reached. <Link href="/pricing" className="underline">View plans</Link></p> : null}
                    <Button onClick={handleNewQuery} disabled={chatDisabled || isSubmitting || !prompt.trim()} className="h-auto whitespace-normal py-2">{isSubmitting ? "Starting discussion…" : task?.action || "Start discussion"}<ArrowRight aria-hidden className="ml-2 h-4 w-4 shrink-0" /></Button>
                </div>
                <p className="text-xs leading-5 text-muted-foreground">Discussions are saved in this project. {project.role === ProjectRole.Admin ? "Review the answer, then use Edit brief below to keep your conclusions." : "Share conclusions with a project admin to update the working brief."} {taskId === "experiment" && "Run the experiment in your research environment, then bring the results back for comparison."}</p>
            </section> : <section className="rounded-xl border border-dashed p-6" aria-labelledby="add-sources-heading">
                <BookOpen aria-hidden className="mb-3 h-6 w-6 text-blue-500" />
                <h2 id="add-sources-heading" className="font-semibold">Start by adding your evidence</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">Add the closest related work and papers with conflicting findings. Then compare their evidence or plan the next experiment.</p>
                <div className="mt-4 flex flex-wrap gap-2"><Button onClick={() => openAddPapers("upload")}>Upload papers</Button><Button variant="outline" onClick={() => openAddPapers("library")}>Add from library</Button></div>
            </section> : <p className="rounded-xl border p-4 text-sm leading-6 text-muted-foreground">You have view access. Open a paper from the project navigation, read the working brief below, or continue reading an existing discussion.</p>}

            <details ref={briefRef} id="research-brief" open={briefOpen} className="group scroll-mt-5 rounded-xl border p-4 sm:p-5" onToggle={event => {
                setBriefOpen(event.currentTarget.open);
                if (event.currentTarget.open) setBriefOpened(true);
            }}>
                <summary className="cursor-pointer text-sm font-semibold">Research brief & mind map<span className="mt-1 block pl-4 text-xs font-normal leading-5 text-muted-foreground">Read at different levels of detail, inspect sources, and update the working synthesis.</span></summary>
                {briefOpened && <div className="mt-6"><ProjectResearchOverview project={project} canEdit={project.role === ProjectRole.Admin} embedded /></div>}
            </details>
            <details className="text-sm">
                <summary className="cursor-pointer font-medium">How to work on this project</summary>
                <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-muted-foreground">
                    <li>Open a paper from the project navigation to read and annotate it.</li>
                    <li>Compare evidence for and against one question. Check the cited passages and differences in experimental setup.</li>
                    <li>Use the working brief to record your provisional answer, unresolved disagreements and what would change your view.</li>
                    <li>Plan a test that separates the explanations. Bring new results back into the evidence comparison.</li>
                </ol>
            </details>
        </div>
    </div>;
}

'use client';

import { useSubscription, isChatCreditAtLimit } from '@/hooks/useSubscription';
import { fetchFromApi, fetchStreamFromApi } from '@/lib/api';
import { useState, useEffect, FormEvent, useRef, useCallback, useMemo, Suspense } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    ChatMessage,
    ChatArtifact,
    ChartGenerationJob,
    MessageTrace,
    Reference,
    TutorState,
} from '@/lib/schema';
import { useAuth } from '@/lib/auth';
import { useProjectWorkspace } from '@/components/project/ProjectWorkspaceProvider';
import { PaperItem } from "@/lib/schema";
import { toast } from "sonner";
import { GraduationCap } from 'lucide-react';
import { ConversationView } from '@/components/ConversationView';
import TutorPanel from '@/components/tutor/TutorPanel';
import { Toggle } from '@/components/ui/toggle';
import { cn } from '@/lib/utils';
import {
    MentionSelection,
    EMPTY_MENTION_SELECTION,
    mentionSelectionIsEmpty,
    selectionToScopeItems,
} from '@/components/chat/MentionAutocomplete';

interface ChatRequestBody {
    user_query: string;
    conversation_id: string | null;
    project_id?: string;
    mentioned_paper_ids?: string[];
    // Omitted for an ordinary answer. 'tutor' has the model teach the
    // project's papers by asking, instead of answering.
    style?: 'tutor';
}

// Whether tutor mode is on for a conversation, remembered per browser. The
// session itself is kept with the conversation on the server.
const TUTOR_MODE_STORAGE_PREFIX = 'openpaper:tutor-mode:conversation:';

const chatLoadingMessages = [
    "Thinking about your question...",
    "Analyzing your knowledge base...",
    "Gathering citations...",
    "Double-checking references...",
    "Formulating a response...",
    "Verifying information...",
    "Crafting insights...",
    "Synthesizing findings...",
]

function ProjectConversationPageContent() {
    const router = useRouter();
    const params = useParams();
    const projectId = params.projectId as string;
    const conversationIdFromUrl = params.conversationId as string;

    const { user, loading: authLoading } = useAuth();
    // Shared workspace data + reader panel — papers open beside the chat.
    const {
        papers: projectPapers,
        isPapersLoading,
        conversations,
        openPaper,
        openPaperIds,
        refreshPaperUrl,
        setCrumb,
        collapseArtifacts,
        pendingDiscussions,
    } = useProjectWorkspace();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isOwner, setIsOwner] = useState<boolean>(true);
    const [mentionSelection, setMentionSelection] = useState<MentionSelection>(EMPTY_MENTION_SELECTION);

    const papers = useMemo(
        () =>
            [...projectPapers].sort(
                (a: PaperItem, b: PaperItem) =>
                    new Date(b.created_at || "").getTime() -
                    new Date(a.created_at || "").getTime(),
            ),
        [projectPapers],
    );

    const [currentMessage, setCurrentMessage] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [conversationId, setConversationId] = useState<string | null>(conversationIdFromUrl);
    const [streamingChunks, setStreamingChunks] = useState<string[]>([]);
    const [streamingReferences, setStreamingReferences] = useState<Reference | undefined>(undefined);
    const [streamingArtifacts, setStreamingArtifacts] = useState<ChatArtifact[]>([]);
    const [streamingChartJobs, setStreamingChartJobs] = useState<ChartGenerationJob[]>([]);
    const [currentLoadingMessageIndex, setCurrentLoadingMessageIndex] = useState(0);
    const [displayedText, setDisplayedText] = useState('');
    const [isTyping, setIsTyping] = useState(false);
    const [statusMessage, setStatusMessage] = useState('');
    const [highlightedInfo, setHighlightedInfo] = useState<{ paperId: string; messageIndex: number } | null>(null);
    const [isCentered, setIsCentered] = useState(false);
    const [isSessionLoading, setIsSessionLoading] = useState(true);
    const [tutorMode, setTutorMode] = useState(false);
    const [tutorState, setTutorState] = useState<TutorState | null>(null);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    // A command from the tutor panel that failed while a draft was in the
    // input, kept so that Retry sends the command and not the draft.
    const retryMessageRef = useRef<string | null>(null);

    useEffect(() => {
        try {
            setTutorMode(localStorage.getItem(`${TUTOR_MODE_STORAGE_PREFIX}${conversationIdFromUrl}`) === 'true');
        } catch {
            // Storage can be unavailable (private mode); the switch still
            // works for this visit.
            setTutorMode(false);
        }
    }, [conversationIdFromUrl]);

    const handleTutorModeChange = useCallback((enabled: boolean) => {
        setTutorMode(enabled);
        try {
            localStorage.setItem(`${TUTOR_MODE_STORAGE_PREFIX}${conversationIdFromUrl}`, String(enabled));
        } catch {
            // See above.
        }
    }, [conversationIdFromUrl]);

    // The session shown belongs to one person's conversation. When either
    // changes under this page, what was on screen is someone else's (or
    // another conversation's) until the new one's own state arrives. A
    // history read or a reply already on its way belongs to the old session
    // too: each notes the session it started under and checks before writing.
    const tutorSessionKey = `${user?.id ?? ''}:${conversationIdFromUrl ?? ''}`;
    const tutorSessionKeyRef = useRef(tutorSessionKey);
    useEffect(() => {
        tutorSessionKeyRef.current = tutorSessionKey;
        setTutorState(null);
    }, [tutorSessionKey]);

    const END_DELIMITER = "END_OF_STREAM";

    const { subscription, refetch: refetchSubscription } = useSubscription();
    const chatCreditLimitReached = isChatCreditAtLimit(subscription);

    const conversationName = useMemo(
        () => conversations.find((c) => c.id === conversationIdFromUrl)?.title ?? '',
        [conversations, conversationIdFromUrl],
    );

    // Surface the conversation title in the workspace breadcrumb.
    useEffect(() => {
        setCrumb(conversationName || 'Chat');
        return () => setCrumb(null);
    }, [conversationName, setCrumb]);

    // Chat scope mirrors the reader tabs: papers open in the reader join the
    // @-mention scope; closing a tab removes them. Diffing against the previous
    // tab set preserves mentions the user typed by hand.
    const prevOpenPaperIdsRef = useRef<string[]>([]);
    useEffect(() => {
        const prev = prevOpenPaperIdsRef.current;
        const added = openPaperIds.filter((id) => !prev.includes(id));
        const removed = prev.filter((id) => !openPaperIds.includes(id));
        prevOpenPaperIdsRef.current = openPaperIds;
        if (added.length === 0 && removed.length === 0) return;
        setMentionSelection((sel) => ({
            ...sel,
            paperIds: [
                ...sel.paperIds.filter((id) => !removed.includes(id)),
                ...added.filter((id) => !sel.paperIds.includes(id)),
            ],
        }));
    }, [openPaperIds]);

    useEffect(() => {
        const CHAT_CREDIT_TOAST_KEY = "chat_credit_limit_toast_shown";
        if (chatCreditLimitReached && !sessionStorage.getItem(CHAT_CREDIT_TOAST_KEY)) {
            toast.error("Nice! You've used your chat credits for the week. Upgrade your plan to continue chatting.", {
                action: {
                    label: "Upgrade",
                    onClick: () => window.location.href = "/pricing",
                },
            });
            sessionStorage.setItem(CHAT_CREDIT_TOAST_KEY, "true");
        }
    }, [chatCreditLimitReached]);

    const handleCitationClick = useCallback((key: string, messageIndex: number) => {
        setHighlightedInfo((prevHighlight) => {
            const message = messages[messageIndex];
            if (!message) return prevHighlight;

            const citation = message.references?.citations?.find(c => String(c.key) === key);
            if (!citation || !citation.paper_id) return prevHighlight;

            // No scroll on click — the reference opens in the side panel, and
            // jumping the chat to the references section is jarring.
            return { paperId: citation.paper_id, messageIndex };
        });
    }, [messages]);


    const fetchMessages = useCallback(async (id: string) => {
        const requestedUnder = tutorSessionKeyRef.current;
        try {
            const response = await fetchFromApi(`/api/projects/conversations/${projectId}/${id}`);
            if (response && response.messages) {
                setMessages(response.messages);
                setIsOwner(response.is_owner);
                setConversationId(id);
                setIsCentered(false);
                // Where the owner's tutoring session in this conversation
                // stands. Another member is never sent one.
                if (response.tutor_state && tutorSessionKeyRef.current === requestedUnder) {
                    // A history read that was slow to return must not roll
                    // the panel back past a turn that has been saved since.
                    const fromHistory: TutorState = response.tutor_state;
                    setTutorState(current =>
                        current && current.turn > fromHistory.turn ? current : fromHistory
                    );
                }
            }
        } catch (error) {
            console.error("Error fetching messages:", error);
            // Go back to the project page
            router.push(`/projects/${projectId}`);
            toast.error("Failed to load conversation history.");
        } finally {
            setIsSessionLoading(false);
        }
    }, [projectId, router]);

    useEffect(() => {
        if (!conversationIdFromUrl) {
            router.push(`/projects/${projectId}`);
            return;
        }

        if (user) {
            const pending = pendingDiscussions.current.get(conversationIdFromUrl);
            const pendingQuery = pending?.query;
            if (pendingQuery) {
                // Apply any @-mention scope carried over from the project page.
                const pendingMentionsRaw = pending?.paperIds.length ? JSON.stringify(pending.paperIds) : null;
                // If mentions were carried over, wait for project papers to load so
                // their titles resolve — otherwise they persist as "Untitled paper".
                // Keep the pending entry until then; this effect re-runs when
                // isPapersLoading flips to false.
                if (pendingMentionsRaw && isPapersLoading) {
                    return;
                }
                setIsSessionLoading(false);
                pendingDiscussions.current.delete(conversationIdFromUrl);
                let pendingMentions: MentionSelection | undefined;
                if (pendingMentionsRaw) {
                    try {
                        const paperIds = JSON.parse(pendingMentionsRaw);
                        if (Array.isArray(paperIds) && paperIds.length > 0) {
                            pendingMentions = { paperIds, projectIds: [], highlights: [] };
                        }
                    } catch {
                        // ignore malformed pending mentions
                    }
                }
                if (pending?.tutor) {
                    // A study session started from the Discuss page. The
                    // switch is set for later turns; this first one is told
                    // outright, since the state above has not rendered yet.
                    handleTutorModeChange(true);
                }
                handleSubmit(null, pendingQuery, pendingMentions, pending?.tutor ? { tutor: true } : undefined);
            } else if (messages.length === 0 && isSessionLoading && !isStreaming) {
                fetchMessages(conversationIdFromUrl);
            }
        } else if (!authLoading) {
            // Only clear messages if we're not loading auth and definitely have no user
            setMessages([]);
            setConversationId(null);
            setIsCentered(true);
            setIsSessionLoading(false);
        }
    }, [conversationIdFromUrl, user, fetchMessages, router, projectId, authLoading, isSessionLoading, isPapersLoading]);

    useEffect(() => {
        if (isStreaming) {
            setTimeout(() => {
                if (messagesEndRef.current) {
                    messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                }
            }, 100);
        }
    }, [isStreaming]);

    useEffect(() => {
        if (!isStreaming) {
            setDisplayedText('');
            setIsTyping(false);
            return;
        }

        const currentMessage = chatLoadingMessages[currentLoadingMessageIndex];
        let charIndex = 0;
        setDisplayedText('');
        setIsTyping(true);

        const typingInterval = setInterval(() => {
            if (charIndex < currentMessage.length) {
                setDisplayedText(currentMessage.slice(0, charIndex + 1));
                charIndex++;
            } else {
                setIsTyping(false);
                clearInterval(typingInterval);
            }
        }, 50);

        return () => clearInterval(typingInterval);
    }, [isStreaming, currentLoadingMessageIndex]);

    useEffect(() => {
        if (!isStreaming) return;

        const messageInterval = setInterval(() => {
            setCurrentLoadingMessageIndex((prev) =>
                (prev + 1) % chatLoadingMessages.length
            );
        }, 11000);

        return () => clearInterval(messageInterval);
    }, [isStreaming]);

    useEffect(() => {
        if (isStreaming) {
            setCurrentLoadingMessageIndex(0);
        }
    }, [isStreaming]);

    // `message` is sent in place of what is typed, and leaves the input as it
    // is: a discussion's first prompt, or a command picked from the tutor
    // panel. `options.tutor` says outright whether this turn goes to the
    // tutor, for a caller that knows before the switch has rendered.
    const handleSubmit = useCallback(async (e: FormEvent | null = null, message?: string, mentionsOverride?: MentionSelection, options?: { tutor?: boolean }) => {
        if (e) {
            e.preventDefault();
        }

        const query = message || currentMessage;

        if (!query.trim() || isStreaming || !conversationId) return;

        // Only in a conversation of the member's own, which is where the
        // server takes a tutor turn and where the switch is shown.
        const asTutor = options?.tutor ?? (isOwner && tutorMode);
        // If the answer is re-sent from scratch, the panel goes back to this.
        const tutorStateBefore = tutorState;
        const sentUnder = tutorSessionKeyRef.current;
        // Whatever failed before, this send replaces it as the thing to retry.
        retryMessageRef.current = null;

        // Get the artifacts panel out of the way so the reply is front-and-center.
        collapseArtifacts();

        // Snapshot @-mention scope for this send, then clear it from the input.
        // A tutor turn has none: it covers the whole project, whatever papers
        // are open beside the chat.
        const submittedMentions = asTutor
            ? EMPTY_MENTION_SELECTION
            : mentionsOverride ?? mentionSelection;
        const userMessage: ChatMessage = {
            role: 'user',
            content: query,
            scope: mentionSelectionIsEmpty(submittedMentions)
                ? undefined
                : selectionToScopeItems(submittedMentions, papers, []),
        };
        setMessages(prev => [...prev, userMessage]);
        // Reset to the reader-tab scope (not empty): papers open in the reader
        // stay in scope until their tabs close; hand-typed mentions are one-shot.
        setMentionSelection({ ...EMPTY_MENTION_SELECTION, paperIds: [...openPaperIds] });

        if (!message) {
            setCurrentMessage('');
        }

        setIsStreaming(true);
        setStreamingChunks([]);
        setStreamingReferences(undefined);
        setStreamingArtifacts([]);
        setStreamingChartJobs([]);
        setError(null);

        const requestBody: ChatRequestBody = {
            user_query: query,
            conversation_id: conversationId,
            project_id: projectId,
        };
        if (submittedMentions.paperIds.length > 0) {
            requestBody.mentioned_paper_ids = submittedMentions.paperIds;
        }
        if (asTutor) {
            requestBody.style = 'tutor';
        }

        try {
            const stream = await fetchStreamFromApi('/api/message/chat/everything', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
            }).catch(fetchError => {
                console.error('Fetch error details:', {
                    name: fetchError.name,
                    message: fetchError.message,
                    stack: fetchError.stack,
                    cause: fetchError.cause
                });
                throw fetchError;
            });

            if (!stream) {
                throw new Error('No stream received from server');
            }

            const reader = stream.getReader();
            const decoder = new TextDecoder();
            let accumulatedContent = '';
            let references: Reference | undefined = undefined;
            const artifacts: ChatArtifact[] = [];
            const chartJobs: ChartGenerationJob[] = [];
            let trace: MessageTrace | undefined = undefined;
            let buffer = '';
            let serverError: string | null = null;

            try {
                while (true) {
                    let result;
                    try {
                        result = await reader.read();
                    } catch (readerError) {
                        console.error('Stream reader error:', {
                            name: readerError instanceof Error ? readerError.name : 'Unknown',
                            message: readerError instanceof Error ? readerError.message : String(readerError),
                            stack: readerError instanceof Error ? readerError.stack : 'No stack',
                        });
                        throw readerError;
                    }

                    const { done, value } = result;

                    if (done) {
                        if (buffer.trim()) {
                            console.warn('Unprocessed buffer at end of stream:', buffer);
                        }
                        break;
                    }

                    if (tutorSessionKeyRef.current !== sentUnder) {
                        // The signed-in user or the conversation changed
                        // while this reply was arriving. It belongs to the
                        // session it was asked in: stop reading it and show
                        // none of it.
                        await reader.cancel();
                        return;
                    }

                    if (!value) {
                        console.warn('Received empty value from stream');
                        continue;
                    }

                    let chunk;
                    try {
                        chunk = decoder.decode(value, { stream: true });
                    } catch (decodeError) {
                        console.error('Error decoding chunk:', decodeError);
                        console.error('Raw chunk value:', value);
                        continue;
                    }

                    buffer += chunk;

                    const parts = buffer.split(END_DELIMITER);
                    buffer = parts.pop() || '';

                    for (const event of parts) {
                        if (!event.trim()) continue;

                        try {
                            const parsedChunk = JSON.parse(event.trim());

                            if (parsedChunk && typeof parsedChunk === 'object' && 'type' in parsedChunk) {
                                const chunkType = parsedChunk.type;
                                const chunkContent = parsedChunk.content;

                                if (chunkType === 'content') {
                                    accumulatedContent += chunkContent;
                                    setStreamingChunks(prev => [...prev, chunkContent]);
                                } else if (chunkType === 'reset') {
                                    // The upstream model connection dropped
                                    // mid-answer and the server re-sent the
                                    // request. The partial answer is not
                                    // resumable, so clear it before the
                                    // replacement answer streams in. Artifacts,
                                    // chart jobs and the trace come from the
                                    // earlier evidence phase and survive it.
                                    console.warn('Stream restarted; discarding partial answer');
                                    accumulatedContent = '';
                                    references = undefined;
                                    setStreamingChunks([]);
                                    setStreamingReferences(undefined);
                                    // The abandoned attempt's session state
                                    // goes with it; the server did not keep
                                    // it either.
                                    if (asTutor && tutorSessionKeyRef.current === sentUnder) {
                                        setTutorState(tutorStateBefore);
                                    }
                                } else if (chunkType === 'tutor_state') {
                                    // A tutor turn's session state, for the
                                    // panel. It is not part of the message,
                                    // and it is sent only once the turn is
                                    // saved.
                                    if (tutorSessionKeyRef.current === sentUnder) {
                                        setTutorState(chunkContent as TutorState);
                                    }
                                } else if (chunkType === 'references') {
                                    references = chunkContent;
                                    setStreamingReferences(chunkContent);
                                } else if (chunkType === 'artifact') {
                                    artifacts.push(chunkContent as ChatArtifact);
                                    setStreamingArtifacts(prev => [...prev, chunkContent as ChatArtifact]);
                                } else if (chunkType === 'chart_job') {
                                    // The chart is being built in the
                                    // background; this is the card to watch it
                                    // by, and it arrives before the answer text.
                                    chartJobs.push(chunkContent as ChartGenerationJob);
                                    setStreamingChartJobs(prev => [...prev, chunkContent as ChartGenerationJob]);
                                } else if (chunkType === 'trace') {
                                    trace = chunkContent as MessageTrace;
                                } else if (chunkType === 'status') {
                                    setStatusMessage(chunkContent);
                                } else if (chunkType === 'error') {
                                    // Noted here and raised below, outside
                                    // this try: thrown from inside it, the
                                    // catch meant for an unparseable event
                                    // took it, and a turn the server refused
                                    // or failed looked like one still waiting.
                                    console.error('Server error in stream:', chunkContent);
                                    serverError = String(chunkContent);
                                } else {
                                    console.warn(`Unknown chunk type: ${chunkType}`, parsedChunk);
                                }
                            } else if (parsedChunk) {
                                console.warn('Received unexpected chunk format:', parsedChunk);
                            }
                        } catch (parseError) {
                            console.error('Error parsing JSON event:', parseError);
                            console.error('Raw event that failed to parse:', JSON.stringify(event));
                            console.error('Event length:', event.length);
                            console.error('Event preview (first 200 chars):', event.substring(0, 200));
                            continue;
                        }

                        if (serverError !== null) {
                            throw new Error(`Server error: ${serverError}`);
                        }
                    }
                }
            } finally {
                // Always release the reader
                try {
                    reader.releaseLock();
                } catch (lockError) {
                    console.warn('Error releasing reader lock:', lockError);
                }
            }

            if (accumulatedContent && tutorSessionKeyRef.current === sentUnder) {
                const finalMessage: ChatMessage = {
                    role: 'assistant',
                    content: accumulatedContent,
                    references: references,
                    artifacts: artifacts.length ? artifacts : undefined,
                    chart_jobs: chartJobs.length ? chartJobs : undefined,
                    trace: trace,
                };
                setMessages(prev => {
                    const newMessages = [...prev, finalMessage];
                    return newMessages;
                });

                // Clear streaming state immediately after adding final message
                setStreamingChunks([]);
                setStreamingReferences(undefined);
                setStreamingArtifacts([]);
                setStreamingChartJobs([]);
            }

        } catch (error) {
            console.error('Error during streaming:', error);

            // Enhanced error logging
            if (error instanceof Error) {
                console.error('Error details:', {
                    name: error.name,
                    message: error.message,
                    stack: error.stack,
                    cause: error.cause
                });
            }

            // Check for specific error types
            if (error instanceof TypeError) {
                if (error.message.includes('input stream') || error.message.includes('stream')) {
                    console.error('Stream-specific TypeError detected');
                    toast.error("Connection interrupted. Please try again.");
                } else if (error.message.includes('fetch')) {
                    console.error('Fetch-related TypeError detected');
                    toast.error("Network error: Please check your connection and try again.");
                } else {
                    console.error('Generic TypeError detected');
                    toast.error(`Type error: ${error.message}`);
                }
            } else if (error instanceof Error && error.name === 'AbortError') {
                console.error('Request was aborted');
                toast.error("Request was cancelled. Please try again.");
            } else if (error instanceof Error && error.message.includes('Server error:')) {
                // Server-sent error, don't wrap it
                toast.error(error.message);
            } else {
                // Generic error handling
                const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
                toast.error(`An error occurred: ${errorMessage}`);
            }

            setMessages(prev => prev.slice(0, -1));
            // What failed goes back in the input to be sent again, unless it
            // was sent in place of a draft that is still sitting there. Then
            // it is kept aside, so that Retry sends it and not the draft.
            if (message && currentMessage.trim()) {
                retryMessageRef.current = message;
            } else {
                setCurrentMessage(query);
            }
            setError(`Streaming error: ${error instanceof Error ? error.message : 'Unknown error'}`);
        } finally {
            setIsStreaming(false);
            setStreamingChunks([]);
            setStreamingReferences(undefined);
            setStreamingArtifacts([]);
            setStreamingChartJobs([]);
            setStatusMessage('');
            refetchSubscription();
        }
    }, [currentMessage, isStreaming, conversationId, projectId, router, refetchSubscription, mentionSelection, papers, openPaperIds, collapseArtifacts, tutorMode, tutorState, isOwner]);

    const [error, setError] = useState<string | null>(null);

    const handleRetry = useCallback(() => {
        setError(null);
        // A failed command is sent again as itself; the draft it left in the
        // input is still not the thing being retried.
        handleSubmit(null, retryMessageRef.current ?? undefined);
    }, [handleSubmit]);

    // A message the learner picked from the tutor panel rather than typed. It
    // is sent on its own: whatever is in the input stays where it is.
    const sendTutorCommand = useCallback((command: string) => {
        setError(null);
        handleSubmit(null, command);
    }, [handleSubmit]);

    const openPathPaper = useCallback((paperId: string) => {
        const paper = papers.find((candidate) => candidate.id === paperId);
        if (paper) openPaper(paper, null);
    }, [papers, openPaper]);

    // Tutor mode is offered where a tutor turn is taken: in a conversation
    // that is the signed-in member's own.
    const canTutor = isOwner && !isSessionLoading;
    const isTutoring = canTutor && tutorMode;
    const tutorDisabledReason = isStreaming
        ? "Wait for the reply to finish"
        : chatCreditLimitReached
            ? "You have used this week's chat credits"
            : undefined;


    return (
        <div className="flex min-h-0 w-full flex-1 flex-col p-2">
            <div className="flex-1 min-h-0">
                <ConversationView
                    messages={messages}
                    isOwner={isOwner}
                    papers={papers}
                    isStreaming={isStreaming}
                    streamingChunks={streamingChunks}
                    streamingReferences={streamingReferences}
                    streamingArtifacts={streamingArtifacts}
                    streamingChartJobs={streamingChartJobs}
                    statusMessage={statusMessage}
                    error={error}
                    isSessionLoading={isSessionLoading}
                    chatCreditLimitReached={chatCreditLimitReached}
                    currentMessage={currentMessage}
                    onCurrentMessageChange={setCurrentMessage}
                    onSubmit={handleSubmit}
                    onRetry={handleRetry}
                    isCentered={isCentered}
                    setIsCentered={setIsCentered}
                    displayedText={displayedText}
                    isTyping={isTyping}
                    handleCitationClick={handleCitationClick}
                    highlightedInfo={highlightedInfo}
                    setHighlightedInfo={setHighlightedInfo}
                    authLoading={authLoading}
                    onRefreshPaperUrl={refreshPaperUrl}
                    onOpenPaperExternal={openPaper}
                    // A tutor turn covers the whole project, so there is
                    // nothing to scope it to.
                    mentionSelection={isTutoring ? EMPTY_MENTION_SELECTION : mentionSelection}
                    onMentionSelectionChange={isTutoring ? undefined : setMentionSelection}
                    mentionPapersOnly
                    projectId={projectId}
                    inputPlaceholder={isTutoring ? "Answer the tutor, or ask to be taught these papers." : undefined}
                    composerAccessory={isTutoring ? (
                        <TutorPanel
                            subject="project"
                            state={tutorState}
                            disabledReason={tutorDisabledReason}
                            onCommand={sendTutorCommand}
                            papers={papers}
                            onOpenPaper={openPathPaper}
                        />
                    ) : undefined}
                    inputToolbar={canTutor ? (
                        <Toggle
                            pressed={tutorMode}
                            onPressedChange={handleTutorModeChange}
                            disabled={isStreaming}
                            title={isStreaming
                                ? "Wait for the reply to finish"
                                : tutorMode
                                    ? "Tutor mode is on: these papers are taught through questions"
                                    : "Tutor mode: learn these papers through questions instead of answers"}
                            className={cn(
                                "h-8 w-fit gap-1.5 px-3 text-xs text-secondary-foreground",
                                "data-[state=on]:bg-blue-100 data-[state=on]:text-blue-700",
                                "dark:data-[state=on]:bg-blue-900 dark:data-[state=on]:text-blue-300"
                            )}
                        >
                            <GraduationCap className="h-4 w-4" />
                            Tutor
                        </Toggle>
                    ) : undefined}
                />
            </div>
        </div>
    );
}

export default function ProjectConversationPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <ProjectConversationPageContent />
        </Suspense>
    );
}

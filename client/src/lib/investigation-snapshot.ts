import type { Investigation } from './investigation';

// The last saved investigation the server gave us, per project, so a view that
// only reads (the canvas) can draw at once on a return visit while the current
// copy loads. Memory only: research text is never written to browser storage.
// Nothing here is ever edited or saved; the document being edited lives in the
// investigation provider.
//
// It belongs to the signed-in user. Sign-out and a change of user empty it and
// start a new session; an answer to a request made in an earlier session is
// neither kept nor shown. A project that is denied loses its entry, and of two
// requests for one project the one that started later decides, so an older
// answer cannot bring back what a later refusal removed, or remove what a later
// answer brought.

export type InvestigationTicket = { projectId: string; session: number; order: number };

const snapshots = new Map<string, Investigation>();
/** Per project, the order of the request that last decided what is kept. */
const settled = new Map<string, number>();
const listeners = new Set<() => void>();
const readers = new Set<() => void>();
const changed = () => { for (const reader of [...readers]) reader(); };
/** Only the most recently used few projects are kept. */
const KEEP = 8;
let session = 0;
let clock = 0;

export const investigationSession = () => session;

/** Called when the session changes, so whoever holds a user's document can let go of it. */
export function subscribeInvestigationSession(listener: () => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
}

/** Called when any kept copy is added, replaced or dropped, so a view drawing one never shows what is no longer kept. */
export function subscribeInvestigationSnapshots(reader: () => void) {
    readers.add(reader);
    return () => { readers.delete(reader); };
}

/** Taken before a request, and handed back with its answer. */
export const askInvestigation = (projectId: string): InvestigationTicket => ({ projectId, session, order: ++clock });

/** False once the user who asked has signed out or changed: the answer is not theirs to see any more. */
export const answerIsCurrent = (ticket: InvestigationTicket) => ticket.session === session;

/**
 * True while no request for the project that started later has been answered, and the user is the same.
 * An answer that no longer stands must not be shown either: it is older than what is already on screen.
 */
export const answerStands = (ticket: InvestigationTicket) => ticket.session === session && ticket.order >= (settled.get(ticket.projectId) ?? 0);

function decides(ticket: InvestigationTicket) {
    if (!answerStands(ticket)) return false;
    settled.set(ticket.projectId, ticket.order);
    return true;
}

/** Keeps the answer and returns true, or returns false when it is not this session's or a later request has already decided. */
export function rememberInvestigation(ticket: InvestigationTicket, document: Investigation) {
    if (!decides(ticket)) return false;
    snapshots.delete(ticket.projectId);
    snapshots.set(ticket.projectId, document);
    for (const oldest of snapshots.keys()) {
        if (snapshots.size <= KEEP) break;
        snapshots.delete(oldest);
    }
    changed();
    return true;
}

/** The server refused this request (401, 403, 404): nothing is kept for the project. */
export function denyInvestigation(ticket: InvestigationTicket) {
    if (decides(ticket) && snapshots.delete(ticket.projectId)) changed();
}

export const recallInvestigation = (projectId: string) => snapshots.get(projectId) ?? null;

/** The project itself is denied: its copy goes, and no request already under way may bring it back. */
export function forgetInvestigation(projectId: string) {
    settled.set(projectId, ++clock);
    if (snapshots.delete(projectId)) changed();
}

export function forgetInvestigations() {
    session += 1;
    snapshots.clear();
    settled.clear();
    for (const listener of [...listeners]) listener();
    changed();
}

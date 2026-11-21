import { flushSync } from "react-dom";

type Transition = { ready?: Promise<unknown>; finished?: Promise<unknown>; updateCallbackDone?: Promise<unknown> };
type TransitionDocument = Document & { startViewTransition?: (update: () => void) => Transition | undefined };

const ignore = () => undefined;

// Runs a state change inside a native view transition, so the old and new
// layout cross-fade instead of jumping. Without the API, or when the user asks
// for reduced motion, the change simply runs.
//
// With a transition the change is applied a frame later, from the browser's
// callback. Callers must not read the new state straight after calling this,
// and anything that has to survive leaving the page in that frame (a saved
// preference) must be written before calling it.
export function withTransition(change: () => void) {
    const page = typeof document === "undefined" ? null : (document as TransitionDocument);
    if (!page?.startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        change();
        return;
    }
    // The callback runs outside React, so the commit must be forced before the browser captures the new state.
    const transition = page.startViewTransition(() => flushSync(change));
    // A transition that is superseded by the next one, or skipped in a hidden
    // tab, rejects these. The change itself has still been applied.
    transition?.ready?.catch(ignore);
    transition?.finished?.catch(ignore);
    transition?.updateCallbackDone?.catch(ignore);
}

"use client";

import { ComponentType, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { withTransition } from "@/lib/transition";

type State = { Panel?: ComponentType; failed?: boolean };

interface DeferredProps {
    // Imports the panel's code. Called again on retry.
    load: () => Promise<ComponentType>;
    // True once the panel is needed. The panel then stays mounted.
    wanted: boolean;
    // True while the user is waiting to see it; decides whether a notice is shown.
    shown: boolean;
    // Used in the notices, e.g. "research brief".
    label: string;
    onDismiss: () => void;
}

// A workspace panel whose code is fetched the first time it is needed. Until
// then it costs nothing; afterwards it behaves as if it had always been mounted.
export function Deferred({ load, wanted, shown, label, onDismiss }: DeferredProps) {
    const [{ Panel, failed }, setState] = useState<State>({});
    const waiting = useRef(shown);
    waiting.current = shown;

    useEffect(() => {
        if (!wanted || Panel || failed) return;
        let live = true;
        load().then(
            loaded => {
                if (!live) return;
                // Code fetched ahead of need mounts silently; a panel the user is waiting for animates in.
                if (waiting.current) withTransition(() => setState({ Panel: loaded }));
                else setState({ Panel: loaded });
            },
            () => { if (live) setState({ failed: true }); },
        );
        return () => { live = false; };
    }, [wanted, Panel, failed, load]);

    // Asking again after a dismissed failure is a fresh attempt.
    useEffect(() => {
        if (!wanted && failed) setState({});
    }, [wanted, failed]);

    if (Panel) return <Panel />;
    if (!shown) return null;
    if (failed) {
        return (
            <div role="alert" data-panel-notice="failed" className="fixed bottom-4 right-4 z-50 max-w-sm rounded-lg border bg-background p-4 text-sm shadow-lg">
                <p>The {label} could not be loaded. Check your connection and try again.</p>
                <div className="mt-3 flex gap-2">
                    <Button size="sm" onClick={() => setState({})}>Try again</Button>
                    <Button size="sm" variant="ghost" onClick={onDismiss}>Dismiss</Button>
                </div>
            </div>
        );
    }
    return (
        <div role="status" data-panel-notice="loading" className="fixed bottom-4 right-4 z-50 rounded-lg border bg-background px-4 py-2 text-sm text-muted-foreground shadow-lg">
            Loading the {label}…
        </div>
    );
}

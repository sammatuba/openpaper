"use client";

import { useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Note = { content: string; etag: string | null };

/** Paper-level notes are independent of annotations and generated summaries. */
export function PaperNotes({ paperId, active }: { paperId: string; active: boolean }) {
    const [note, setNote] = useState<Note | null>(null);
    const [draft, setDraft] = useState("");
    const [editing, setEditing] = useState(false);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const endpoint = `${API_BASE_URL}/api/paper/note?${new URLSearchParams({ paper_id: paperId })}`;

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const response = await fetch(endpoint, { credentials: "include", cache: "no-store" });
            if (response.status === 404) {
                setNote(null);
            } else if (response.ok) {
                const data = await response.json();
                setNote({ content: data.content ?? "", etag: response.headers.get("ETag") });
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch {
            setError("Could not load paper notes. Please try again.");
        } finally {
            setLoading(false);
        }
    }, [endpoint]);

    useEffect(() => {
        if (active && !editing) void load();
    }, [active, editing, load]);

    const save = async () => {
        if (note && !note.etag) {
            setError("This server did not provide a note version. Refresh before editing.");
            return;
        }
        setSaving(true);
        setError("");
        try {
            const response = await fetch(endpoint, {
                method: note ? "PUT" : "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json", ...(note?.etag ? { "If-Match": note.etag } : {}) },
                body: JSON.stringify({ content: draft }),
            });
            if (response.status === 412 || response.status === 409) {
                setError("This note changed elsewhere. Your draft is preserved below; copy it before cancelling and refreshing the latest note.");
                return;
            }
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            setLoading(true);
            setEditing(false); // load the new version before allowing another edit
        } catch {
            setError("Could not confirm the save. Your draft is preserved; copy it, cancel and refresh before retrying.");
        } finally {
            setSaving(false);
        }
    };

    return (
        <section className="h-full overflow-y-auto p-5" aria-label="Paper notes">
            <div className="flex items-center justify-between gap-4 mb-4">
                <h2 className="text-lg font-semibold">Paper notes</h2>
                {!editing && <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>Refresh</Button>
                    <Button size="sm" disabled={loading || !!error || (!!note && !note.etag)} onClick={() => { setDraft(note?.content ?? ""); setEditing(true); }}>Edit</Button>
                </div>}
            </div>
            {error && <p role="alert" className="text-sm text-destructive mb-3">{error}</p>}
            {editing ? <div className="space-y-3">
                <label htmlFor="paper-note-draft" className="text-sm text-muted-foreground">Markdown note</label>
                <Textarea id="paper-note-draft" className="min-h-64 font-mono text-sm" value={draft} onChange={event => setDraft(event.target.value)} disabled={saving} />
                <div className="flex gap-2">
                    <Button size="sm" onClick={() => void save()} disabled={saving}>Save</Button>
                    <Button variant="outline" size="sm" onClick={() => { setEditing(false); setError(""); }} disabled={saving}>Cancel</Button>
                </div>
            </div> : loading ? <p className="text-sm text-muted-foreground">Loading notes…</p> : !error && (
                note?.content ? <div className="prose prose-sm dark:prose-invert max-w-none break-words"><Markdown remarkPlugins={[remarkGfm]}>{note.content}</Markdown></div>
                    : <p className="text-sm text-muted-foreground">No paper notes yet.</p>
            )}
        </section>
    );
}

"use client";

import { useEffect, useRef, useState } from 'react';
import { FileUp, Pencil } from 'lucide-react';
import { fetchFromApi } from '@/lib/api';
import type { TextFoldDocument } from '@/lib/schema';
import { normalizeProjectMarkdown, parseTextFold, RESEARCH_TEMPLATE } from '@/lib/textfold';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useProjectWorkspace } from './ProjectWorkspaceProvider';

export function EditProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
    const { project, refetchProject } = useProjectWorkspace();
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [imported, setImported] = useState<TextFoldDocument | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [discarded, setDiscarded] = useState(false);
    const fileInput = useRef<HTMLInputElement>(null);
    const wasOpen = useRef(false);

    useEffect(() => {
        // A background project refresh must not replace an unsaved draft.
        if (open && !wasOpen.current && project) {
            setTitle(project.title);
            setDescription(project.description || '');
            setImported(project.research_brief || null);
            setError(null);
            setDiscarded(false);
        }
        wasOpen.current = open;
    }, [open, project]);

    const editSource = (next: string) => {
        setDescription(next);
        if (imported) { setImported(null); setDiscarded(true); }
    };
    const importFile = async (file: File | undefined) => {
        if (!file) return;
        try {
            if (file.size > 1_000_000) throw new Error('Choose a Textfold JSON file under 1 MB.');
            const doc = parseTextFold(JSON.parse(await file.text()));
            setImported(doc);
            setDiscarded(false);
            setError(null);
        } catch (e) { setError(e instanceof Error ? e.message : 'Could not read the Textfold file. Choose a valid JSON export.'); }
        if (fileInput.current) fileInput.current.value = '';
    };
    const save = async () => {
        if (!project || saving || !title.trim()) return;
        setSaving(true);
        setError(null);
        try {
            await fetchFromApi(`/api/projects/${project.id}`, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title.trim(), description, research_brief: imported }),
            });
            await refetchProject();
            onOpenChange(false);
        } catch {
            setError('Could not save the research brief. Your draft is still here. Try saving again.');
        } finally { setSaving(false); }
    };

    return <Dialog open={open} onOpenChange={next => { if (!saving) onOpenChange(next); }}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl" onInteractOutside={e => e.preventDefault()}>
            <DialogHeader>
                <DialogTitle>Edit research brief</DialogTitle>
                <DialogDescription>Start with a question. Use headings to connect evidence, disagreements and the experiment that would resolve them.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-2">
                <div className="space-y-2"><Label htmlFor="project-title">Project title</Label><Input id="project-title" value={title} onChange={e => setTitle(e.target.value)} disabled={saving} /></div>
                <div className="space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2"><Label htmlFor="project-brief">Research brief · Markdown</Label>
                        <Button type="button" variant="ghost" size="sm" className="text-xs" disabled={saving} onClick={() => editSource(`${description.trim() ? `${description.trim()}\n\n` : ''}${RESEARCH_TEMPLATE}`)}>{description.trim() ? 'Append framework' : 'Use research framework'}</Button>
                    </div>
                    <Textarea id="project-brief" value={description} onChange={e => editSource(e.target.value)} disabled={saving} className="min-h-64 font-mono text-sm" placeholder="Start with ## The question" />
                    <p className="text-xs leading-5 text-muted-foreground">Lead each paragraph with its point so it reads well at every detail level. Include primary sources, search date, caveats and what would change your mind.</p>
                    {!description.includes('\n') && /\s#{1,6}\s/.test(description) && <Button type="button" variant="outline" size="sm" className="text-xs" disabled={saving} onClick={() => editSource(normalizeProjectMarkdown(description))}>Separate inline headings · review before saving</Button>}
                </div>
                <div className="rounded-lg border p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">Textfold reading levels</p>
                        <Button type="button" variant="outline" size="sm" className="gap-1.5 text-xs" disabled={saving} onClick={() => fileInput.current?.click()}><FileUp className="h-3.5 w-3.5" />Import Textfold JSON</Button>
                        <input ref={fileInput} type="file" accept=".json,application/json" className="sr-only" aria-label="Import Textfold JSON file" disabled={saving} onChange={e => void importFile(e.target.files?.[0])} />
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">{imported ? `${imported.title} · ${imported.sections.length} sections · ${imported.provenance.ai_generated ? 'AI-written summaries' : 'Provided excerpts'}. These levels will be saved with the project.` : 'The brief folds locally using its own sentences. Import a Textfold export to retain its generated summaries and sentence anchors.'}</p>
                    {imported && <Button type="button" size="sm" variant="ghost" className="mt-2 h-auto px-0 text-xs" disabled={saving} onClick={() => { setImported(null); setDiscarded(true); }}>Use local excerpts instead</Button>}
                    {discarded && <p className="mt-2 text-xs text-muted-foreground">Saved reading levels will be replaced by local excerpts when you save. You can import new levels after editing.</p>}
                </div>
                {error && <p role="alert" className="rounded-md border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
            </div>
            <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button><Button onClick={() => void save()} disabled={saving || !title.trim()}>{saving ? 'Saving…' : 'Save brief'}</Button></DialogFooter>
        </DialogContent>
    </Dialog>;
}

export function EditProjectButton({ className }: { className?: string }) {
    const [open, setOpen] = useState(false);
    return <><button onClick={() => setOpen(true)} className={className} aria-label="Edit project title and research brief" title="Edit project"><Pencil className="h-3 w-3" /></button><EditProjectDialog open={open} onOpenChange={setOpen} /></>;
}

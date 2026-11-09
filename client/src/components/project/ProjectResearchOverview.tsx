"use client";

import { useMemo, useState } from 'react';
import { BookOpen, CircleHelp, Pencil } from 'lucide-react';
import type { Project } from '@/lib/schema';
import { projectResearchBrief, researchQuestion, RESEARCH_FRAMEWORK } from '@/lib/textfold';
import { TextFoldReader } from '@/components/textfold/TextFoldReader';
import { Button } from '@/components/ui/button';
import { EditProjectDialog } from './EditProjectDialog';

export function ProjectResearchOverview({ project, canEdit, embedded = false }: { project: Project; canEdit: boolean; embedded?: boolean }) {
    const [editing, setEditing] = useState(false);
    const { document: doc, invalid } = useMemo(() => projectResearchBrief(project), [project]);
    const question = researchQuestion(doc) || doc.sections[0]?.takeaway || project.title;
    const covered = RESEARCH_FRAMEWORK.map(item => ({ ...item, section: doc.sections.find(s => item.match.test(s.title) && s.units.some(u => u.full.trim())) }));
    const missing = covered.filter(item => !item.section);
    const hasContent = doc.sections.some(s => s.units.length > 0);

    return <div className="mb-8 space-y-6">
        <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
                <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground"><BookOpen className="h-3.5 w-3.5" />Research overview<span className="rounded-full border px-2 py-0.5">Working brief</span></div>
                {embedded ? <h2 className="text-lg font-semibold">Working synthesis</h2> : <h1 className="text-2xl font-semibold leading-tight tracking-tight [overflow-wrap:anywhere]">{project.title}</h1>}
            </div>
            {canEdit && <Button variant="outline" size="sm" onClick={() => setEditing(true)} className="shrink-0 gap-1.5 text-xs"><Pencil className="h-3 w-3" />Edit brief</Button>}
        </div>
        <p className="max-w-3xl text-xs leading-5 text-muted-foreground">Organized around a disputed question, following <a href="https://www.lesswrong.com/posts/tn4WSyrqr7ozGLjRy/people-should-resolve-tensions-in-ai-safety-research" className="underline" target="_blank" rel="noreferrer">David Africa’s research-tension framework</a>. These are project statements; literature coverage and novelty need source-backed review.</p>
        {invalid && <p role="alert" className="rounded-md border p-3 text-sm">The saved reading levels could not be opened. Showing the project description. Edit the brief to replace the imported levels.</p>}
        {hasContent ? <>
            <div className="grid gap-3 sm:grid-cols-2">
                {covered.filter(item => item.key === 'relevance' || item.key === 'landscape').map(item => <div key={item.key} className="rounded-xl border bg-muted/20 p-4">
                    <p className="mb-2 text-xs font-medium text-muted-foreground">{item.title}</p>
                    <p className="text-sm leading-6 [overflow-wrap:anywhere]">{item.section?.takeaway || item.prompt}</p>
                    {!item.section && <span className="mt-2 block text-xs text-muted-foreground">Not yet assessed in this brief</span>}
                </div>)}
            </div>
            <TextFoldReader key={`${project.id}-${JSON.stringify(doc)}`} document={doc} question={question} />
        </> : <div className="rounded-xl border border-dashed p-6">
            <CircleHelp className="mb-3 h-5 w-5 text-muted-foreground" />
            <h2 className="mb-2 font-medium">Start with the uncertainty</h2>
            <p className="text-sm leading-6 text-muted-foreground">What question could this project help resolve? Add a research brief to connect the evidence, explain disagreements and identify the next useful experiment.</p>
            {canEdit && <Button variant="outline" size="sm" className="mt-4" onClick={() => setEditing(true)}>Write a research brief</Button>}
        </div>}
        {!!missing.length && hasContent && <details className="rounded-lg border p-4 text-sm">
            <summary className="cursor-pointer font-medium">Open questions in this brief · {missing.length} areas to develop</summary>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">Based on section headings only. A missing section is a writing gap, not a finding about the research.</p>
            <ul className="mt-3 space-y-3">{missing.map(item => <li key={item.key}><span className="text-xs font-medium">{item.title}</span><p className="mt-1 text-xs leading-5 text-muted-foreground">{item.prompt}</p></li>)}</ul>
        </details>}
        {canEdit && <EditProjectDialog open={editing} onOpenChange={setEditing} />}
    </div>;
}

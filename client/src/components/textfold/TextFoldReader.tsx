"use client";

import { useEffect, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import { Download } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { serializeTextFold } from '@/lib/textfold';
import { TEXTFOLD_COMMIT, toUpstreamDocument, upstreamPage } from '@/lib/textfold-upstream';
import type { TextFoldDocument } from '@/lib/schema';

let templateRequest: Promise<string> | undefined;
function loadTemplate() {
    return templateRequest ||= fetch('/vendor/textfold/template.html').then(r => {
        if (!r.ok) throw new Error('Reader assets could not load.');
        return r.text();
    }).catch(error => { templateRequest = undefined; throw error; });
}

export function downloadFold(doc: TextFoldDocument) {
    let serialized: string;
    try { serialized = serializeTextFold(doc); }
    catch { toast.error('Could not export this brief as Textfold. It must fit the supported format and 1 MB size limit.'); return; }
    const url = URL.createObjectURL(new Blob([serialized], {type:'application/json'}));
    const a = document.createElement('a');
    a.href = url;
    a.download = `${doc.id.replace(/[^a-zA-Z0-9_-]/g,'-') || 'research-brief'}.textfold.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
}

export function TextFoldReader({document:doc,question}: {document:TextFoldDocument;question?:string}) {
    const {user} = useAuth();
    const {resolvedTheme} = useTheme();
    const [page, setPage] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [ready, setReady] = useState(false);
    const [warnings, setWarnings] = useState(0);
    const frame = useRef<HTMLIFrameElement>(null);
    const expectedRevision = useRef('');
    useEffect(() => {
        if (!user?.id) return;
        let active = true;
        setReady(false);
        setError(null);
        loadTemplate().then(async template => {
            if (!active) return;
            const data = toUpstreamDocument(doc,user.id,question);
            const digest = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(doc.sections)));
            const revision = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2,'0')).join('');
            if (!active) return;
            data.saved = data.meta.version = revision;
            expectedRevision.current = revision;
            setWarnings(data.openpaper.warnings.length);
            setPage(upstreamPage(template,data,resolvedTheme === 'dark' ? 'dark' : 'light'));
        }).catch(() => { if (active) setError('Could not open the Textfold reader. Reload to try again; the original brief is below.'); });
        return () => {active=false;};
    },[doc,user?.id,resolvedTheme,question]);
    useEffect(() => {
        const receive = (event: MessageEvent) => {
            if (event.source === frame.current?.contentWindow && event.origin === location.origin && event.data?.type === 'openpaper:textfold-ready' && event.data.commit === TEXTFOLD_COMMIT && event.data.revision === expectedRevision.current) setReady(true);
        };
        addEventListener('message',receive);
        return () => removeEventListener('message',receive);
    },[]);
    useEffect(() => {
        if (!page || ready) return;
        const timer = setTimeout(() => setError('Textfold did not finish opening. Reload to try again; the original brief is below.'),15000);
        return () => clearTimeout(timer);
    },[page,ready]);
    return <div className="min-w-0 space-y-3" aria-label="Folded research brief">
        <div className="flex flex-wrap items-center justify-between gap-2">
            <div><h2 className="text-sm font-semibold">Explore with Textfold</h2><p className="mt-1 text-xs text-muted-foreground">Zoom from the map to every word. Click a paragraph to unfold it.</p></div>
            <Button variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={() => downloadFold(doc)}><Download className="h-3.5 w-3.5" />Export Textfold</Button>
        </div>
        <p className="text-xs text-muted-foreground">{doc.provenance.local ? 'Local excerpts · first sentences, no new assessment' : doc.provenance.ai_generated ? `AI-written summaries${doc.provenance.model ? ` · ${doc.provenance.model}` : ''}` : 'Provided reading levels'}. Full and Brief preserve source wording.</p>
        {warnings > 0 && <p className="text-xs text-muted-foreground">{warnings} passage{warnings === 1 ? '' : 's'} use full source context at Brief because their Markdown crosses sentence boundaries.</p>}
        {error && <p role="alert" className="rounded-md border p-3 text-sm">{error}</p>}
        {!error && <div className="overflow-hidden rounded-xl border" data-textfold-commit={TEXTFOLD_COMMIT} data-reader-ready={ready}>
            {!ready && <p role="status" className="p-3 text-xs text-muted-foreground">Opening Textfold…</p>}
            {page && <iframe ref={frame} title="Textfold research reader" srcDoc={page} sandbox="allow-scripts allow-same-origin allow-downloads allow-popups allow-modals allow-forms" className="h-[75svh] min-h-80 max-h-[760px] w-full border-0" />}
        </div>}
        <p className="text-xs leading-5 text-muted-foreground">Uses <a className="underline" href={`https://github.com/chenxiachan/textfold/tree/${TEXTFOLD_COMMIT}`} target="_blank" rel="noreferrer">Textfold’s upstream reader</a>. Reader highlights stay in this browser for this version of the brief; they are separate from shared project content.</p>
        <details className="rounded-lg border p-4 text-xs text-muted-foreground"><summary className="cursor-pointer">Original brief and source anchors</summary>
            {doc.sections.map(s => <section key={s.id} className="mt-4 space-y-2"><h3 className="font-semibold">{s.title}</h3>{s.units.map(u => <div key={u.id} className="space-y-2"><pre className="whitespace-pre-wrap break-words font-mono leading-6 [overflow-wrap:anywhere]">{u.full}</pre><p>Supporting sentences: {u.evidence.map(i => i+1).join(', ') || 'None recorded'}</p></div>)}</section>)}
        </details>
    </div>;
}

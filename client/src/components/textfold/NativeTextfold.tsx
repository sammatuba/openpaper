"use client";

import { useEffect, useRef, useState } from 'react';
import type { TextFoldDocument } from '@/lib/schema';
import { toUpstreamDocument } from '@/lib/textfold-upstream';
import { mountTextfold } from '@/lib/textfold-native';

type Props = {
    document: TextFoldDocument;
    identity: string;
    userId: string;
    onSelectUnit?: (id: string) => void;
    onOpenSource?: (id:string)=>void;
};

// Kept separate from the legacy reader until the complete compatibility gate passes.
export function NativeTextfold({ document: doc, identity, userId, onSelectUnit,onOpenSource }: Props) {
    const root = useRef<HTMLDivElement>(null);
    const scroller = useRef<HTMLDivElement>(null);
    const reader = useRef<ReturnType<typeof mountTextfold> | null>(null);
    const callback = useRef(onSelectUnit);
    callback.current = onSelectUnit;
    const sourceCallback=useRef(onOpenSource);sourceCallback.current=onOpenSource;
    const [dark,setDark]=useState(false);
    useEffect(()=>{const sync=()=>setDark(window.document.documentElement.classList.contains('dark'));sync();const observer=new MutationObserver(sync);observer.observe(window.document.documentElement,{attributes:true,attributeFilter:['class']});return()=>observer.disconnect();},[]);
    const activeTheme=useRef<'light'|'dark'>('light');
    activeTheme.current=dark?'dark':'light';
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        if (!root.current || !scroller.current) return;
        setError(null);
        let active=true;
        const data=toUpstreamDocument(doc,userId);
        crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(doc.sections))).then(hash=>{
            if(!active||!root.current||!scroller.current)return;
            const version=Array.from(new Uint8Array(hash),value=>value.toString(16).padStart(2,'0')).join('');
            data.saved=data.meta.version=version;
            reader.current=mountTextfold({root:root.current,scrollElement:scroller.current,document:data,identity:identity+':'+version,theme:activeTheme.current,onSelectUnit:id=>callback.current?.(id),onOpenSource:id=>sourceCallback.current?.(id)});
        }).catch(()=>{if(active)setError('The folded preview could not open. Your document is preserved.');});
        return () => { active=false;reader.current?.destroy();reader.current=null; };
        // Theme updates are applied to the existing instance below.
    },[doc,identity,userId]);
    useEffect(()=>{reader.current?.setTheme(dark ? 'dark' : 'light');},[dark]);
    return <div aria-label="Folded document preview">
        {error && <p role="alert">{error}</p>}
        <button className="mb-2 rounded border px-2 py-1 text-xs" onClick={()=>{
            const annotations=reader.current?.exportLocalAnnotations();if(!annotations)return;
            const url=URL.createObjectURL(new Blob([JSON.stringify(annotations,null,2)],{type:'application/json'}));
            const link=window.document.createElement('a');link.href=url;link.download='local-reader-annotations.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        }}>Export local reader annotations</button>
        <div ref={scroller} className="relative h-[65svh] min-h-80 overflow-auto overscroll-contain">
            <div ref={root} />
        </div>
    </div>;
}

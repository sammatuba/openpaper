import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { TextFoldDocument } from './schema';
import { markdownReferences } from './textfold';

// Adapter only: rendering, word morphs, zoom, local expansion and maps are the
// pinned upstream Textfold reader in public/vendor/textfold (Apache-2.0).
export const TEXTFOLD_COMMIT = '92ad625ab6887bf0060374c1fd86a558513baed2';
type Token = { t?: string; a?: string; s?: number; f?: string; m?: number; k?: number };
type Atom = { kind: string; html: string; text: string; alt: string };
const escape = (s: string) => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]!));

export function toUpstreamDocument(doc: TextFoldDocument, userId: string, question?: string) {
    const references = markdownReferences(doc);
    const atoms: Record<string, Atom> = {};
    const atomIds = new Map<string, string>();
    const units: Record<string, unknown> = {};
    const aliases: Record<string, string> = Object.create(null);
    doc.sections.forEach((s, i) => {
        aliases[s.id] = `op-s-${i}`;
        s.units.forEach((u, j) => { aliases[u.id] = `op-u-${i}-${j}`; });
    });
    const warnings: string[] = [];
    const words = new Intl.Segmenter(doc.lang || 'en', {granularity:'word'});
    const html = (text: string) => renderToStaticMarkup(createElement(Markdown, {
        remarkPlugins:[remarkGfm], components:{
            img: ({alt}) => createElement('span', null, `[Image: ${alt || 'source figure'}]`),
            a: ({href,title,children}) => href ? createElement('a',{href,title,
                ...(href.startsWith('#') ? {} : {target:'_blank',rel:'noopener noreferrer'})},children) : createElement('span',{title},children),
        },
    },`${text}\n\n${references}`));
    const tokenize = (text: string): Token[] => {
        const root = new DOMParser().parseFromString(html(text), 'text/html').body;
        const result: Token[] = [];
        const space = () => { if (result.length) result[result.length - 1].s = 1; };
        const visit = (node: Node, font = '') => {
            if (node.nodeType === Node.TEXT_NODE) {
                for (const part of words.segment(node.textContent || '')) {
                    if (/^\s+$/.test(part.segment)) space();
                    else result.push({t:part.segment, ...(font ? {f:font} : {})});
                }
                return;
            }
            if (!(node instanceof Element)) return;
            if (node.matches('a, pre, table, code, math')) {
                const serialized = node.outerHTML;
                let id = atomIds.get(serialized);
                if (!id) {
                    id = `a${atomIds.size}`;
                    atomIds.set(serialized, id);
                    atoms[id] = {kind:node.matches('a') ? 'link' : 'inline',html:serialized,text:node.textContent || '',alt:node.textContent || ''};
                }
                result.push({a:id});
                return;
            }
            const nextFont = node.matches('strong,b') ? `${font} b`.trim() : node.matches('em,i') ? `${font} i`.trim() : font;
            if (node.matches('p,li,blockquote,br,h1,h2,h3,h4,h5,h6')) space();
            node.childNodes.forEach(child => visit(child, nextFont));
            if (node.matches('p,li,blockquote,br,h1,h2,h3,h4,h5,h6')) space();
        };
        root.childNodes.forEach(node => visit(node));
        if (result.length) delete result[result.length - 1].s;
        return result;
    };
    const plain = (t: Token) => t.a ? atoms[t.a].text : t.t || '';
    const signature = (t: Token) => plain(t).normalize('NFKC').toLocaleLowerCase();
    const align = (written: Token[], source: Token[]) => {
        const positions = new Map<string, number[]>();
        source.forEach((token, i) => {
            const key = signature(token);
            if (!positions.has(key)) positions.set(key, []);
            positions.get(key)!.push(i);
        });
        let cursor = 0;
        return written.map(token => {
            const candidates = positions.get(signature(token)) || [];
            let lo = 0, hi = candidates.length;
            while (lo < hi) { const mid = (lo + hi) >>> 1; if (candidates[mid] < cursor) lo = mid + 1; else hi = mid; }
            const at = candidates[lo];
            if (at === undefined) return {...token};
            cursor = at + 1;
            return {...token,m:at};
        });
    };
    const blocks: Record<string, unknown>[] = [];
    const chunks = doc.sections.map(section => {
        const sectionId = aliases[section.id];
        const ids: string[] = [];
        blocks.push({k:'h',chunk:sectionId});
        for (const unit of section.units) {
            const unitId = aliases[unit.id];
            const full = tokenize(unit.full);
            if (!full.length) continue; // A reference definition has no rendered words.
            // The public source excerpt becomes exact ranges in the rendered token
            // stream. Internal ranges may be finer than linguistic sentences;
            // canonical sentence anchors remain untouched in the saved document.
            const kept = new Set<number>();
            let cursor = 0, matched = true;
            for (const sentence of unit.brief) {
                const quote = tokenize(sentence);
                let found = -1;
                for (let i = cursor; quote.length && i + quote.length <= full.length; i++) {
                    if (quote.every((t, j) => t.a ? t.a === full[i + j].a : t.t === full[i + j].t)) { found = i; break; }
                }
                if (found < 0) { matched = false; break; }
                for (let i = found; i < found + quote.length; i++) kept.add(i);
                cursor = found + quote.length;
            }
            if (!matched) {
                // Showing extra original context is preferable to a wrong quote.
                full.forEach((_, i) => kept.add(i));
                warnings.push(unit.id);
            }
            const key = align(tokenize(unit.key), full);
            const take = align(tokenize(unit.takeaway), full);
            let topicCursor = 0;
            const topic = tokenize(unit.topic).map(t => {
                const at = take.findIndex((candidate, i) => i >= topicCursor && signature(candidate) === signature(t));
                if (at >= 0) topicCursor = at + 1;
                return {...t,...(at < 0 ? {} : {k:at})};
            });
            const role = ['context','gap','claim','method','setup','result','analysis','limitation'].includes(String(unit.role)) ? unit.role : 'context';
            units[unitId] = {id:unitId,role:unit.kind === 'list item' ? 'item' : 'paragraph',chunk:sectionId,
                toks:full,sents:full.map((_, i) => [i,i+1]),
                lad:{role,ev:[...kept].sort((a,b) => a-b),brief:key,take,tn:take.length,topic,model:doc.provenance.local ? 'local' : doc.provenance.model || 'provided'}};
            ids.push(unitId);
            blocks.push({k:'u',chunk:sectionId,u:unitId});
        }
        const take = tokenize(section.takeaway);
        const topicWords = tokenize(section.topic);
        return {id:sectionId,num:typeof section.num === 'string' ? section.num : '',title:section.title,
            html:escape(section.title),level:Math.min(5,section.depth+1),units:ids,
            lad:{take,topic:take.flatMap((t,i) => topicWords.some(word => signature(word) === signature(t)) ? [i] : [])}};
    });
    const sectionIds = new Set(doc.sections.map(s => s.id));
    const edges = doc.links.filter(l => !sectionIds.has(l.from) && aliases[l.from] in units && (sectionIds.has(l.to) || aliases[l.to] in units))
        .map(l => ({f:aliases[l.from],t:aliases[l.to],tk:sectionIds.has(l.to) ? 'chunk' : 'unit',rel:['supports','builds_on','qualifies','explains','ref'].includes(l.rel) ? l.rel : 'ref'}));
    return {meta:{id:`openpaper:${userId}:${doc.id}`,version:'',title:question || doc.title,authors:[],label:'OpenPaper research brief',lang:doc.lang,langs:[doc.lang],source:{kind:'markdown'},local:doc.provenance.local},
        app:false,atoms,units,chunks,blocks,bib:'',edges,alias:aliases,katex:null,mermaid:null,lang:doc.lang,
        saved:'',openpaper:{commit:TEXTFOLD_COMMIT,warnings,provenance:doc.provenance}};
}

export function upstreamPage(template: string, data: ReturnType<typeof toUpstreamDocument>, theme: string) {
    const base = new URL('/vendor/textfold/', location.href).href;
    const csp = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src data:; font-src 'self'; connect-src 'none'; form-action 'none'; base-uri 'none'";
    const head = `<meta http-equiv="Content-Security-Policy" content="${csp}"><link rel="stylesheet" href="${base}reader.css"><style>.tagline,.langpick,.paper-head .authors,.chatbtn,.chat,[data-act="ask"]{display:none!important}.tk pre,.tk table{max-width:100%;overflow:auto}.topbar{padding:10px 16px}.doc{padding-top:12px}</style>`;
    const scripts = `<script src="${base}i18n.js"></script><script src="${base}reader.js"></script><script>document.documentElement.dataset.theme=${JSON.stringify(theme)};window.__reader.setLevel(0);document.querySelector('[data-view="map"]')?.click();window.parent.postMessage({type:'openpaper:textfold-ready',commit:${JSON.stringify(TEXTFOLD_COMMIT)},revision:${JSON.stringify(data.saved)}},${JSON.stringify(location.origin)});</script>`;
    const parts: Record<string, string> = {TITLE:escape(data.meta.title),HEAD:head,CLASS:'static',SIDEBAR:'',
        DATA:JSON.stringify(data).replace(/</g,'\\u003c'),SCRIPTS:scripts};
    return template.replace(/\{\{(TITLE|HEAD|CLASS|SIDEBAR|DATA|SCRIPTS)\}\}/g, (_, key: string) => parts[key]);
}

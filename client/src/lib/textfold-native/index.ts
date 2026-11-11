import DOMPurify from 'dompurify';
import { boot, css, template } from './engine';

type Options = {
    root: HTMLElement; scrollElement: HTMLElement; document: unknown; identity: string;
    theme: 'light' | 'dark'; onSelectUnit?: (id: string) => void;
    onOpenSource?: (id: string) => void; onSelection?: (text: string) => void;
};

function mountInstance(options: Options) {
    const { root, scrollElement } = options;
    const owner = root.ownerDocument;
    const shadow = root.shadowRoot || root.attachShadow({ mode: 'open' });
    const surface = owner.createElement('div');
    surface.className = 'native-surface native-body';
    surface.tabIndex = 0;
    surface.dataset.theme = options.theme;
    const style = owner.createElement('style');
    style.textContent = css + `
      :host { display:block; min-width:0; }
      .native-surface { position:relative; min-height:360px; overflow:clip; }
      .topbar, footer.zoom { position:sticky; z-index:10; }
      .topbar { top:0; } footer.zoom { bottom:0; }
      .native-surface .doc { min-width:0; }
      .native-overlays { position:sticky; top:0; height:0; width:100%; z-index:30; pointer-events:none; }
      .native-overlays > .zhost,.native-overlays > #ghosts,.native-overlays > .lightbox { height:var(--native-view-height); bottom:auto; }
      .native-overlays > .mmap { height:calc(var(--native-view-height) - 60px); bottom:auto; }
      .savebtn,.type-full,.cmpbtn,.svdlg,.chatbtn,.chat,.brand,.ty-row:has([data-mode]),.ty-row:has([data-style]) { display:none !important; }
    `;
    surface.innerHTML = DOMPurify.sanitize(template);
    shadow.replaceChildren(style, surface);
    const overlays=owner.createElement('div');overlays.className='native-overlays';surface.prepend(overlays);
    surface.style.setProperty('--native-view-height',scrollElement.clientHeight+'px');
    const appendToSurface=(...nodes:Node[])=>{
        for(const node of nodes){surface.append(node);
            if(node instanceof HTMLElement && getComputedStyle(node).position==='absolute'){
                const pointerEvents=getComputedStyle(node).pointerEvents;
                overlays.append(node);node.style.pointerEvents=pointerEvents;
            }
        }
    };
    const ghosts=shadow.getElementById('ghosts');if(ghosts)appendToSurface(ghosts);
    let alive = true;
    const controller = new AbortController();
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const frames = new Set<number>();
    const cleanups: (() => void)[] = [];
    const memory = new Map<string, string>();
    const prefix = `openpaper:textfold:native:${options.identity}:`;
    const storage = {
        getItem: (key: string) => owner.defaultView!.localStorage.getItem(prefix + key),
        setItem: (key: string, value: string) => owner.defaultView!.localStorage.setItem(prefix + key, value),
        removeItem: (key: string) => owner.defaultView!.localStorage.removeItem(prefix + key),
    };
    const listen = (target: EventTarget, type: string, callback: EventListener, config?: boolean | AddEventListenerOptions) => {
        if (!alive) return;
        // Selection events originate on the owner document; all other reader events stay local.
        const actual = target === owner ? (type === 'selectionchange' ? owner : surface) : target;
        const handler = (event: Event) => {
            if (!alive) return;
            if ((actual === surface || actual === scrollElement) && event.type === 'keydown' && (event.composedPath()[0] as Element)?.closest('input,textarea,[contenteditable]')) return;
            if (actual === owner && !shadow.contains(owner.getSelection()?.anchorNode || null)) return;
            callback(event);
        };
        actual.addEventListener(type, handler, { ...(typeof config === 'boolean' ? {capture:config} : config), signal: controller.signal });
    };
    const scope = {
        guard: (callback: (...args: unknown[])=>unknown) => (...args:unknown[]) => alive ? callback(...args) : undefined,
        appendToSurface, surface, shadow, storage, title: '', disconnected: undefined,
        session: {getItem:(key:string)=>memory.get(key)||null,setItem:(key:string,value:string)=>memory.set(key,value),removeItem:(key:string)=>memory.delete(key)},
        location: {hash:'',search:'',origin:owner.location.origin,href:owner.location.href},
        get stylesheet() { return style.sheet; },
        get left() { return scrollElement.getBoundingClientRect().left; },
        get top() { return scrollElement.getBoundingClientRect().top; },
        get width() { return scrollElement.clientWidth; },
        get height() { return scrollElement.clientHeight; },
        get scrollTop() { return scrollElement.scrollTop; },
        byId: (id: string) => shadow.getElementById(id),
        hit: (x:number,y:number) => shadow.elementFromPoint(x+scrollElement.getBoundingClientRect().left,y+scrollElement.getBoundingClientRect().top),
        rect: (element: Element) => {
            const r = element.getBoundingClientRect(), s = scrollElement.getBoundingClientRect();
            return new DOMRect(r.x-s.x,r.y-s.y,r.width,r.height);
        },
        scrollBy: (x:number,y:number) => scrollElement.scrollBy(x,y),
        scrollTo: (position:ScrollToOptions) => scrollElement.scrollTo(position),
        listen,
        on: (type:string, callback:EventListener, config?:AddEventListenerOptions) => listen(type==='scroll' ? scrollElement : surface,type,callback,config),
        off: () => {},
        noNetwork: () => Promise.reject(new Error('Standalone Textfold services are disabled.')),
        delay: (callback:()=>void, ms=0) => {
            if (!alive) return 0;
            const id = setTimeout(()=>{timers.delete(id);if(alive)callback();},ms); timers.add(id);return id;
        },
        clearDelay: (id:ReturnType<typeof setTimeout>) => {clearTimeout(id);timers.delete(id);},
        frame: (callback:FrameRequestCallback) => {
            if (!alive) return 0;
            const id=requestAnimationFrame(time=>{frames.delete(id);if(alive)callback(time);});frames.add(id);return id;
        },
        cancelFrame: (id:number)=>{cancelAnimationFrame(id);frames.delete(id);},
    };
    const resizeObserver = new ResizeObserver(() => {if(alive){surface.style.setProperty('--native-view-height',scrollElement.clientHeight+'px');surface.dispatchEvent(new Event('resize'));}});
    resizeObserver.observe(scrollElement);
    cleanups.push(()=>resizeObserver.disconnect());
    const destroy = () => {
        if (!alive) return;
        alive=false;controller.abort();surface.getAnimations({subtree:true}).forEach(animation=>animation.cancel());
        timers.forEach(clearTimeout);frames.forEach(cancelAnimationFrame);
        timers.clear();frames.clear();cleanups.forEach(fn=>fn());shadow.replaceChildren();
    };
    // Do not permit document data to enable standalone network/conversion features.
    if (!options.document || typeof options.document !== 'object') { destroy(); throw new Error('Invalid reader document.'); }
    const data = structuredClone(options.document) as Record<string, unknown>;
    if (!data.meta || typeof data.meta !== 'object' || !data.units || !data.atoms || !Array.isArray(data.chunks) || !Array.isArray(data.blocks)) {destroy();throw new Error('Invalid reader document.');}
    const meta = data.meta as Record<string,unknown>;
    if (typeof meta.abs_url === 'string') {
        try { const url=new URL(meta.abs_url);if(!['https:','http:'].includes(url.protocol))delete meta.abs_url; } catch { delete meta.abs_url; }
    }
    data.app=false;delete data.pdfAt;delete data.pdfmap;delete data.katex;delete data.mermaid;
    const sanitize = (value: unknown): unknown => {
        if (Array.isArray(value)) return value.map(sanitize);
        if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key,item])=>[key, typeof item==='string' && (key==='html'||key==='title') ? DOMPurify.sanitize(item,{FORBID_TAGS:['script','iframe','form','style','link','img','video','audio','source','object','embed'],FORBID_ATTR:['style']}) : sanitize(item)]));
        return value;
    };
    let engine: ReturnType<typeof boot>;
    try { engine=boot(sanitize(data),scope); } catch (error) { destroy();throw error; }
    listen(surface,'click',event=>{
        const element=(event.target as Element).closest('[data-u]');
        if(element)options.onSelectUnit?.(element.getAttribute('data-u')!);
    });
    listen(surface,'mouseup',()=>scope.delay(()=>{
        const selection=owner.getSelection();
        if(selection?.anchorNode?.getRootNode()===shadow)options.onSelection?.(selection.toString());
    }));
    listen(surface,'click',event=>{
        const anchor=(event.target as Element).closest('a[href]');
        if(anchor&&options.onOpenSource){const url=new URL(anchor.getAttribute('href')!,owner.location.href);const finding=url.searchParams.get('finding');if(url.origin===owner.location.origin&&/^\/projects\/[^/]+\/evidence$/.test(url.pathname)&&finding){event.preventDefault();event.stopPropagation();options.onOpenSource(finding);return;}}
        const link=(event.target as Element).closest('[data-source-id]');
        if(link){event.preventDefault();options.onOpenSource?.(link.getAttribute('data-source-id')!);}
    });
    return {
        setLevel: (level:number) => {if(alive)engine.setLevel(level);},
        setTheme: (theme:'light'|'dark') => {if(alive)surface.dataset.theme=theme;},
        focusUnit: (id:string) => {if(alive)shadow.querySelector(`[data-u="${CSS.escape(id)}"]`)?.scrollIntoView({block:'nearest'});},
        exportLocalAnnotations: () => Object.fromEntries(Object.keys(owner.defaultView!.localStorage).filter(k=>k.startsWith(prefix)&&k.includes('dr-notes:')).map(k=>[k,owner.defaultView!.localStorage.getItem(k)])),
        destroy,
    };
}


export function mountTextfold(options:Options){
    let currentOptions=options;
    let instance=mountInstance(currentOptions);
    let destroyed=false;
    return {
        setDocument(document:unknown,identity:string){if(destroyed)return;instance.destroy();currentOptions={...currentOptions,document,identity};instance=mountInstance(currentOptions);},
        setLevel(level:number){if(!destroyed)instance.setLevel(level);},
        setTheme(theme:'light'|'dark'){currentOptions={...currentOptions,theme};if(!destroyed)instance.setTheme(theme);},
        focusUnit(id:string){if(!destroyed)instance.focusUnit(id);},
        exportLocalAnnotations(){return destroyed?{}:instance.exportLocalAnnotations();},
        destroy(){if(!destroyed){destroyed=true;instance.destroy();}},
    };
}

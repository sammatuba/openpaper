const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const http=require('node:http');
const {chromium}=require(process.env.OPENPAPER_PLAYWRIGHT_MODULE||'playwright');
const esbuild=require(process.env.OPENPAPER_ESBUILD_MODULE||'esbuild');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const bundle=await esbuild.build({stdin:{contents:`
 import {mountTextfold} from './src/lib/textfold-native';
 import {foldMarkdown} from './src/lib/textfold';
 import {toUpstreamDocument} from './src/lib/textfold-upstream';
 window.mount=()=>{
 const doc=foldMarkdown('# Question\\nDoes control compose?\\n\\n## Evidence\\nA result was observed. A caveat remains. Another detail matters.','Synthetic','fixture');
 const data=toUpstreamDocument(doc,'synthetic');
 data.meta.abs_url='javascript:window.nativeInjected=true';
 window.nativeData=data;
 window.nativeLongData=toUpstreamDocument(foldMarkdown('# Long document\\n'+Array.from({length:50},(_,i)=>'## Evidence '+i+'\\nA synthetic paragraph records result '+i+'. Another detail remains.').join('\\n\\n'),'Long synthetic','long-fixture'),'synthetic');
 window.readers=[0,1].map(i=>mountTextfold({root:document.getElementById('r'+i),scrollElement:document.getElementById('s'+i),document:data,identity:'synthetic:'+i,theme:'light'}));
 };`,resolveDir:root,loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',define:{'process.env.NODE_ENV':'"production"'}});
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/bundle.js'?'text/javascript':'text/html');res.end(req.url==='/bundle.js'?bundle.outputFiles[0].text:'<input id="outside"><div style="display:flex"><div id="s0" style="height:600px;overflow:auto;width:48%"><div id="r0"></div></div><div id="s1" style="height:600px;overflow:auto;width:48%"><div id="r1"></div></div></div><script src="/bundle.js"></script>');});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try {
 browser=await chromium.launch({executablePath:process.env.OPENPAPER_CHROMIUM,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 await page.addInitScript(()=>{
  const listeners=new Set(),timers=new Set(),frames=new Set(),observers=new Set();
  const add=EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener=function(type,callback,options){
   if(options&&typeof options==='object'&&options.signal&&!options.signal.aborted){const record={};listeners.add(record);add.call(options.signal,'abort',()=>listeners.delete(record),{once:true});}
   return add.call(this,type,callback,options);
  };
  const delay=window.setTimeout.bind(window),clear=window.clearTimeout.bind(window);
  window.setTimeout=(callback,ms,...args)=>{const id=delay(()=>{timers.delete(id);callback(...args);},ms);timers.add(id);return id;};
  window.clearTimeout=id=>{timers.delete(id);clear(id);};
  const frame=window.requestAnimationFrame.bind(window),cancel=window.cancelAnimationFrame.bind(window);
  window.requestAnimationFrame=callback=>{const id=frame(time=>{frames.delete(id);callback(time);});frames.add(id);return id;};
  window.cancelAnimationFrame=id=>{frames.delete(id);cancel(id);};
  const Resize=window.ResizeObserver;
  window.ResizeObserver=class extends Resize{observe(element,options){observers.add(this);return super.observe(element,options);}disconnect(){observers.delete(this);super.disconnect();}};
  window.nativeDiagnostics=()=>({listeners:listeners.size,timers:timers.size,frames:frames.size,observers:observers.size});
 });
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto('http://127.0.0.1:'+server.address().port);
 const baseline=await page.evaluate(()=>window.nativeDiagnostics());
 await page.evaluate(()=>window.mount());
 assert.equal(await page.locator('iframe').count(),0);
 assert.equal(await page.locator('#r0 a[href^=\"javascript:\"]').count(),0);
 await page.locator('#r0 .native-surface').focus();await page.keyboard.press('5');await page.waitForTimeout(750);
 assert.equal(await page.locator('#r0 .doc').getAttribute('data-level'),'0');
 await page.keyboard.press('1');await page.waitForTimeout(750);
 assert.equal(await page.locator('#r0 .doc').getAttribute('data-level'),'4');
 await page.keyboard.press('Control+f');
 const finder=page.locator('#r0 .findbar input');
 await finder.fill('result');await page.keyboard.press('Escape');
 const texts=[];
 for(const level of [0,1,2,3,4]){
 await page.evaluate(l=>window.readers[0].setLevel(l),level);await page.waitForTimeout(750);
 assert.equal(await page.locator('#r0 .doc').getAttribute('data-level'),String(level));
 assert.equal(await page.locator('#r1 .doc').getAttribute('data-level'),'4');
 texts.push(await page.locator('#r0 .doc').innerText());
 }
 assert.ok(new Set(texts).size>=3,'Levels must change actual rendered text');
 assert.match(texts[4],/Another detail matters/);
 const artifacts=path.resolve(root,'../.meos/artifacts/investigation-workspace');fs.mkdirSync(artifacts,{recursive:true});
 assert.equal(await page.locator('#r0 .zhost').evaluate(el=>getComputedStyle(el).backgroundColor),'rgba(0, 0, 0, 0)','Animation host must not hide the document at rest');
 assert.ok(await page.locator('#r0 .u .tk').first().evaluate(el=>el.getBoundingClientRect().width)>0);
 await page.screenshot({path:path.join(artifacts,'native-smoke-desktop.png'),fullPage:true});
 await page.evaluate(()=>window.readers[0].setLevel(2));await page.waitForTimeout(800);
 const unit=page.locator('#r0 .u').first();await unit.click();await page.waitForTimeout(800);
 assert.equal(await unit.getAttribute('data-l'),'4','Click expands one actual source paragraph locally');
 assert.equal(await page.locator('#r0 .doc').getAttribute('data-level'),'2');
 await page.evaluate(()=>window.readers[0].setLevel(0));await page.waitForTimeout(800);
 await page.locator('#r0 [data-view="map"]').click();
 await page.locator('#r0 .mmap:not([hidden])').waitFor();
 assert.ok(await page.locator('#r0 .mmap svg').count()>0,'Actual upstream topic map rendered');
 await page.locator('#r0 .mmap .mm-leaf').first().click();await page.waitForTimeout(800);
 assert.equal(await page.locator('#r0 .doc').getAttribute('data-level'),'2','Topic map leaf returns to its actual evidence paragraph');
 await page.evaluate(()=>window.readers[0].setLevel(4));await page.waitForTimeout(800);
 await page.locator('#r0 .native-surface').evaluate(el=>{
  const r=el.getBoundingClientRect();const options={bubbles:true,cancelable:true,clientX:r.left+100,clientY:r.top+100};
  el.dispatchEvent(new MouseEvent('gesturestart',options));
  const change=new MouseEvent('gesturechange',options);Object.defineProperty(change,'scale',{value:0.5});el.dispatchEvent(change);
  el.dispatchEvent(new MouseEvent('gestureend',options));
 });await page.waitForTimeout(1100);
 assert.notEqual(await page.locator('#r0 .doc').getAttribute('data-level'),'4','Pinch gesture changes the actual engine level');
 assert.equal(await page.evaluate(()=>window.scrollY),0,'Reader gestures leave page scrolling unchanged');
 await page.evaluate(()=>window.readers[0].setLevel(4));await page.waitForTimeout(800);
 await page.locator('#r0 #zoombar').hover();await page.mouse.wheel(0,200);await page.waitForTimeout(1100);
 assert.notEqual(await page.locator('#r0 .doc').getAttribute('data-level'),'4','Wheel over the local bar changes actual reader level');
 assert.equal(await page.locator('#r1 .doc').getAttribute('data-level'),'4');
 await page.evaluate(()=>window.readers[0].setDocument(window.nativeData,'replacement-version'));
 await page.evaluate(()=>window.readers[0].setLevel(3));await page.waitForTimeout(800);
 assert.equal(await page.locator('#r0 .doc').getAttribute('data-level'),'3','Stable factory handle controls the replacement document');
 await page.evaluate(()=>{window.readers[0].setDocument(window.nativeLongData,'long-version');window.readers[0].setLevel(0);});await page.waitForTimeout(900);
 await page.locator('#s0').evaluate(el=>{el.scrollTop=300;});await page.waitForTimeout(100);
 assert.ok(await page.locator('#s0').evaluate(el=>el.scrollTop)>0);
 await page.locator('#r0 [data-view="map"]').click();await page.locator('#r0 .mmap:not([hidden])').waitFor();
 const overlayBounds=await page.locator('#r0 .mmap').boundingBox(),scrollBounds=await page.locator('#s0').boundingBox();
 assert.ok(overlayBounds.y>=scrollBounds.y-1&&overlayBounds.y<scrollBounds.y+100,'Map overlay stays aligned to scrolled reader viewport');
 await page.locator('#r0 .mmap .mm-leaf').first().click();await page.waitForTimeout(800);
 await page.locator('#outside').fill('');await page.keyboard.type('12345');assert.equal(await page.locator('#outside').inputValue(),'12345');
 await page.evaluate(()=>window.readers[0].setTheme('dark'));
 assert.equal(await page.locator('#r0 .native-surface').getAttribute('data-theme'),'dark');
 assert.equal(await page.locator('html').getAttribute('data-theme'),null);
 await page.evaluate(()=>{window.readers[0].setLevel(0);window.readers[0].destroy();});
 for(let i=0;i<20;i++){await page.evaluate(()=>{window.readers.forEach(r=>r.destroy());window.mount();});}
 await page.evaluate(()=>window.readers.forEach(r=>r.destroy()));
 await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>{window.mount();window.readers[0].setLevel(1);});
 await page.waitForTimeout(100);
 assert.equal(await page.locator('#r0 .doc').getAttribute('data-level'),'1');
 await page.evaluate(()=>window.readers.forEach(r=>r.destroy()));
 await page.waitForTimeout(800);assert.deepEqual(errors,[]);
 assert.deepEqual(await page.evaluate(()=>window.nativeDiagnostics()),baseline,'Tracked listeners, timers, frames and observers return to baseline');
 console.log('Native two-instance, five-level, keyboard/finder, visible text, safe URL/theme and 20-cycle lifecycle accounting passed.');
 } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});

// Deterministic, build-time extraction of the pinned Apache-2.0 reader.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const vendor = path.join(root, 'public/vendor/textfold');
const out = path.join(root, 'src/lib/textfold-native');
const manifest = JSON.parse(fs.readFileSync(path.join(vendor, 'UPSTREAM.json')));
const hash = text => crypto.createHash('sha256').update(text).digest('hex');
for (const [name, record] of Object.entries(manifest.files)) {
  if (hash(fs.readFileSync(path.join(vendor,name))) !== record.sha256) throw Error(`Pinned input changed: ${name}`);
}
let reader = fs.readFileSync(path.join(vendor,'reader.js'),'utf8');
reader = reader.replace('(() => {', 'function boot(D, scope) {').replace(/\}\)\(\);\s*$/, '}');
reader = reader.replace("  const D = JSON.parse(document.getElementById('paper-data').textContent);", '');
reader = reader.replace('const I18N = window.DR_I18N;', 'const I18N = nativeI18n;');
reader = reader.replace('window.__reader = {', 'return {');
reader = reader.replace('async fetch({ kind, filename })', 'async fetchBinary({ kind, filename })');
reader = reader.replaceAll('document.documentElement','scope.surface')
 .replaceAll('document.body','scope.surface').replaceAll('document.head','scope.surface')
 .replaceAll('document.getElementById','scope.byId').replaceAll('document.querySelectorAll','scope.shadow.querySelectorAll.bind(scope.shadow)')
 .replaceAll('document.querySelector','scope.shadow.querySelector.bind(scope.shadow)')
 .replaceAll('document.elementFromPoint','scope.hit')
 .replaceAll('document.getAnimations()', 'scope.surface.getAnimations({subtree:true})')
 .replaceAll('document.styleSheets','[scope.stylesheet]')
 .replaceAll('(?:html|:root)', '(?:html|:root|\\.native-surface)')
 .replaceAll('scope.surface.append(', 'scope.appendToSurface(')
 .replaceAll('scope.surface.appendChild(', 'scope.appendToSurface(')
 .replaceAll('document.activeElement','scope.shadow.activeElement')
 .replaceAll('window.scrollBy','scope.scrollBy').replaceAll('window.scrollTo','scope.scrollTo')
 .replace(/(?<![.\w])scrollBy\(/g,'scope.scrollBy(')
 .replaceAll('document.title', 'scope.title')
 .replaceAll('window.DRApp', 'scope.disconnected').replaceAll('window.desktop','scope.disconnected')
 .replaceAll('window.showSaveFilePicker','scope.disconnected')
 .replaceAll('localStorage','scope.storage').replaceAll('sessionStorage','scope.session')
 .replaceAll('location.', 'scope.location.')
 .replace(/\binnerWidth\b/g, 'scope.width').replace(/\binnerHeight\b/g,'scope.height').replace(/\bscrollY\b/g,'scope.scrollTop')
 .replace(/(?<![.\w])requestAnimationFrame\(/g,'scope.frame(')
 .replace(/(?<![.\w])cancelAnimationFrame\(/g,'scope.cancelFrame(')
 .replace(/(?<![.\w])setTimeout\(/g,'scope.delay(')
 .replace(/(?<![.\w])clearTimeout\(/g,'scope.clearDelay(')
 .replace(/(?<![.\w])fetch\(/g,'scope.noNetwork(')
 .replace(/(?<![.\w])addEventListener\(/g,'scope.on(')
 .replace(/(?<![.\w])removeEventListener\(/g,'scope.off(');
// Rewrite all listener registrations and DOM rectangle reads structurally.
const parsed = ts.createSourceFile('engine.js',reader,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
const transformed = ts.transform(parsed, [context => {
 const visit = node => {
  if (ts.isPropertyAccessExpression(node) && ['clientX','clientY'].includes(node.name.text)) return ts.factory.createBinaryExpression(ts.factory.updatePropertyAccessExpression(node,ts.visitNode(node.expression,visit),node.name),ts.SyntaxKind.MinusToken,ts.factory.createPropertyAccessExpression(ts.factory.createIdentifier('scope'),node.name.text==='clientX'?'left':'top'));
  if (ts.isCallExpression(node) && node.expression.kind===ts.SyntaxKind.ImportKeyword) return ts.factory.createCallExpression(ts.factory.createPropertyAccessExpression(ts.factory.createIdentifier('scope'),'noNetwork'),undefined,[]);
  if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
   const access = node.expression;
   if (access.name.text === 'then') return ts.factory.createCallExpression(ts.visitNode(node.expression,visit),undefined,node.arguments.map(a=>ts.factory.createCallExpression(ts.factory.createPropertyAccessExpression(ts.factory.createIdentifier('scope'),'guard'),undefined,[ts.visitNode(a,visit)])));
   if (access.name.text === 'addEventListener') return ts.factory.createCallExpression(ts.factory.createPropertyAccessExpression(ts.factory.createIdentifier('scope'),'listen'),undefined,[ts.visitNode(access.expression,visit),...node.arguments.map(a=>ts.visitNode(a,visit))]);
   if (access.name.text === 'getBoundingClientRect') return ts.factory.createCallExpression(ts.factory.createPropertyAccessExpression(ts.factory.createIdentifier('scope'),'rect'),undefined,[ts.visitNode(access.expression,visit)]);
  }
  return ts.visitEachChild(node,visit,context);
 }; return node=>ts.visitNode(node,visit);
}]);
reader = ts.createPrinter().printFile(transformed.transformed[0]);
transformed.dispose();
const i18n = fs.readFileSync(path.join(vendor,'i18n.js'),'utf8').replace('window.DR_I18N =','const nativeI18n =');
const css = fs.readFileSync(path.join(vendor,'reader.css'),'utf8').replace(/:root/g,'.native-surface').replace(/(^|[\s,>+~(])(html|body)(?=[\s.#:\[>+~),{]|$)/gm,(_match,prefix,tag)=>prefix+(tag==='body'?'.native-body':'.native-surface')).replace(/position: fixed/g,'position: absolute');
const template = fs.readFileSync(path.join(vendor,'template.html'),'utf8').split('<body>')[1].split('<script')[0].replace('{{SIDEBAR}}','');
const output = '/* eslint-disable @typescript-eslint/no-unused-vars -- preserve pinned upstream engine locals */\n// Generated by scripts/build-textfold-native.cjs; do not edit. Apache-2.0.\n'+i18n+'\n'+reader+'\nexport { boot };\nexport const css = '+JSON.stringify(css)+';\nexport const template = '+JSON.stringify(template)+';\n';
const outputs = {'engine.js':output, 'manifest.json':JSON.stringify({commit:manifest.commit,engine_sha256:hash(output),patches:'scripts/build-textfold-native.cjs'},null,2)+'\n'};
for (const [name, text] of Object.entries(outputs)) {
 const destination=path.join(out,name);
 if (process.argv.includes('--check')) { if (fs.readFileSync(destination,'utf8')!==text) throw Error(`Generated drift: ${name}`); }
 else fs.writeFileSync(destination,text);
}
console.log('Native extraction reproduced; pinned inputs verified.');

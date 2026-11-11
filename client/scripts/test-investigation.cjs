// Validate graph/bounds in the browser module without any application or provider call.
const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),assert=require('node:assert/strict');
const filename=path.resolve(__dirname,'../src/lib/investigation.ts'),m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));
m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {validateInvestigation,emptyInvestigation,downloadInvestigation}=m.exports;
validateInvestigation(emptyInvestigation());
for(const update of [{version:true},{version:2},{unexpected:1}])assert.throws(()=>validateInvestigation({...emptyInvestigation(),...update}));
const claim={id:'40000000-0000-4000-8000-000000000001',statement:'Conditional',reasoning:'',caveats:'',archived:false};
let doc=emptyInvestigation();doc.claims=[claim];validateInvestigation(doc);doc.claims.push(claim);assert.throws(()=>validateInvestigation(doc));
doc=emptyInvestigation();doc.case.question='文'.repeat(20001);assert.throws(()=>validateInvestigation(doc));
doc=emptyInvestigation();doc.claims=Array.from({length:34},(_,i)=>({...claim,id:require('node:crypto').randomUUID(),reasoning:'文'.repeat(20000)}));assert.throws(()=>validateInvestigation(doc));
doc=emptyInvestigation();doc.manuscript.sections=[{id:require('node:crypto').randomUUID(),title:'Draft',blocks:[{id:require('node:crypto').randomUUID(),kind:'paragraph',text:'Authored',claim_ids:[claim.id],finding_ids:[],provenance:{kind:'human'},dependency_pins:{}}]}];assert.throws(()=>validateInvestigation(doc));
// Offline recovery never embeds captured source text or bibliography.
doc=emptyInvestigation();doc.findings=[{id:require('node:crypto').randomUUID(),label:'Authored label',observed_result:'',author_interpretation:'',our_interpretation:'',setup:{model:'',task:'',training:'',intervention:'',evaluation:'',other:''},limitations:'',archived:false,source:{kind:'anchored',paper_id:require('node:crypto').randomUUID(),start_line:1,end_line:1,quote:'PRIVATE CAPTURE',title:'PRIVATE TITLE',source_sha256:'0'.repeat(64),quote_sha256:'0'.repeat(64)}}];
doc.manuscript.sections=[{id:require('node:crypto').randomUUID(),title:'Quotes',blocks:[{id:require('node:crypto').randomUUID(),kind:'source_quote',text:'',claim_ids:[],finding_ids:[doc.findings[0].id],provenance:{kind:'assembled'},dependency_pins:{},quote_snapshot:structuredClone(doc.findings[0].source)}]}];
let blob;global.URL.createObjectURL=value=>(blob=value,'blob:test');global.URL.revokeObjectURL=()=>{};global.window={document:{createElement:()=>({click(){}})}};
downloadInvestigation(doc,false);blob.text().then(text=>{assert.ok(!text.includes('PRIVATE CAPTURE'));assert.ok(!text.includes('PRIVATE TITLE'));assert.equal(JSON.parse(text).saved,false);console.log('Client strict graph, Unicode bounds and offline recovery redaction passed.');}).catch(error=>{console.error(error);process.exitCode=1;});

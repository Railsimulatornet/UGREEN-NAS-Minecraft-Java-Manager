const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..'),staticRoot=path.join(root,'mcj/static'),context={};
vm.createContext(context);
for(const file of ['i18n.js','setup-wizard.js','server-property-help.js'])vm.runInContext(fs.readFileSync(path.join(staticRoot,file),'utf8'),context);
vm.runInContext('this.messages=TEXT;',context);
test('loaded user-facing language catalogues cover the same keys',()=>{
 assert.deepEqual(Object.keys(context.messages.de).sort(),Object.keys(context.messages.en).sort());
});
test('literal labels in the application never fall back to untranslated keys',()=>{
 for(const file of ['app.js','setup-wizard.js']){
  const source=fs.readFileSync(path.join(staticRoot,file),'utf8');
  for(const found of source.matchAll(/\b(?:t|paragraph|button|field|modal|pill)\(\s*['"]([A-Za-z][A-Za-z0-9_]*)['"](?!\s*\+)/g))for(const language of ['de','en'])assert(context.messages[language][found[1]],file+': '+language+'/'+found[1]);
 }
});
test('unknown errors have a readable message without reflecting provider text',()=>{
 const source=fs.readFileSync(path.join(staticRoot,'app.js'),'utf8');
 vm.runInContext("let state={language:'de'};const t=key=>TEXT[state.language][key]||key;"+source.match(/^const errorText=.*$/m)[0]+"this.showError=errorText;",context);
 assert.equal(context.showError('PRIVATE_PROVIDER_DETAILS'),context.messages.de.unexpectedError);
 assert.equal(context.showError('curseforge_api_key_required'),context.messages.de.curseforge_api_key_required);
});

test('inline error panels do not render untranslated provider codes',()=>{const source=fs.readFileSync(path.join(staticRoot,'app.js'),'utf8');assert(!/paragraph\(error\.code/.test(source));});

test('unfamiliar status labels stay readable instead of exposing an internal key',()=>{
 const source=fs.readFileSync(path.join(staticRoot,'app.js'),'utf8'),sandbox={node:(tag,props)=>props};vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync(path.join(staticRoot,'i18n.js'),'utf8')+"\nlet state={language:'en'};const t=key=>TEXT[state.language][key]||key;"+source.match(/^function pill\(.*$/m)[0]+'\nthis.label=label=>pill(label).text;',sandbox);
 assert.equal(sandbox.label('state_PRIVATE_ERROR'),'Unavailable');assert.equal(sandbox.label(null),'Unavailable');
 assert.equal(sandbox.label('state_running'),'Running');
});

test('server job names describe the action without claiming it has finished',()=>{
 const source=fs.readFileSync(path.join(staticRoot,'app.js'),'utf8');
 const sandbox={};vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync(path.join(staticRoot,'i18n.js'),'utf8'),sandbox);
 vm.runInContext("let state={language:'de'};const t=key=>TEXT[state.language][key]||key;"+
  source.match(/^function serverJobTitle\(.*$/m)[0]+'\n'+source.match(/^function jobTitle\(.*$/m)[0]+
  '\nthis.title=(language,job)=>{state.language=language;return jobTitle(job)};this.event=(language,event)=>TEXT[language][event];',sandbox);
 const labels={de:{start:'Minecraft-Server starten',stop:'Minecraft-Server stoppen',restart:'Minecraft-Server neu starten'},
  en:{start:'Start Minecraft server',stop:'Stop Minecraft server',restart:'Restart Minecraft server'}};
 for(const language of ['de','en'])for(const operation of ['start','stop','restart']){
  for(const state of ['pending','waiting','running','succeeded','failed','cancelled'])
   assert.equal(sandbox.title(language,{kind:'server',operation,state}),labels[language][operation]);
  assert.notEqual(sandbox.title(language,{kind:'server',operation}),sandbox.event(language,'server_'+operation));
 }
 for(const language of ['de','en'])assert.equal(sandbox.title(language,{kind:'server',operation:'PRIVATE_UNKNOWN_VALUE'}),context.messages[language].maintenanceAction);
 // The confirmation review must use the same action label as the queue.
 assert(source.includes("else if(kind==='server')lines.push(serverJobTitle(payload.operation))"));
});

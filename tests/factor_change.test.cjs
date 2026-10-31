const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../mcj/static/app.js'),'utf8');
function fixture(language='de',factor='email'){
 const requests=[],views=[];
 function node(tag,props={},...children){return {tag,...props,children:children.flat(Infinity).filter(Boolean),append(...items){this.children.push(...items);},prepend(...items){this.children.unshift(...items);}};}
 const sandbox={state:{language,user:{factor},csrf:'old-csrf'},node,
  button:(label,action)=>node('button',{label,action}),paragraph:(key)=>node('p',{key}),
  input:(type,value,props)=>node('input',{type,value,...props}),field:(label,child)=>node('label',{label},child),
  form:(children,label,submit)=>node('form',{label,submit},children),
  modal:(title,body)=>views.push({surface:'modal',title,body}),authBody:(title,body)=>views.push({surface:'auth',title,body}),
  profile:()=>views.push({surface:'modal',title:'profile'}),
  displayCodes:(codes,inModal)=>views.push({surface:inModal?'modal':'auth',title:'backupCodes',codes}),
  api:async(url,body)=>{requests.push({url,body});if(url.endsWith('/confirm')){
    if(body.code==='bad')throw {code:'invalid_factor'};
    return {csrf:'new-csrf',backup_codes:['disposable-recovery-fixture']};
   }if(url.endsWith('/status'))return {configured:true,can_configure:false};return {challenge:'disposable-challenge',qr:'data:image/svg+xml;base64,fixture',secret:'disposable-key'};}
 };
 vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../mcj/static/i18n.js'),'utf8')+'\nconst t=key=>TEXT[state.language][key]||key;'+
  source.slice(source.indexOf('function factorLabel('),source.indexOf('function downloadText('))+'\nthis.panel=factorPanel;this.setup=factorSetup;',sandbox);
 return {sandbox,requests,views};
}
function descendants(node){return [node,...(node.children||[]).flatMap(descendants)];}
function control(view,label){const found=descendants(view.body).find(node=>node.label===label);assert.ok(found,label);return found;}

test('profile names the active method and changing or cancelling does not start enrollment',async()=>{
 for(const language of ['de','en'])for(const factor of ['email','totp']){
  const f=fixture(language,factor),panel=f.sandbox.panel(),text=descendants(panel).map(n=>n.text||'').join(' ');
  assert.match(text,factor==='email'?/E-Mail|Email/:/TOTP/);
  await control({body:panel},'changeFactor').action();
  assert.equal(f.views.at(-1).title,'changeFactor');assert.equal(f.views.at(-1).surface,'modal');
  await control(f.views.at(-1),'cancel').action();
  assert.equal(f.views.at(-1).title,'profile');assert.deepEqual(f.requests,[]);assert.equal(f.sandbox.state.user.factor,factor);
 }
});

test('changing either way keeps the old method on rejection and shows new recovery codes only after confirmation',async()=>{
 for(const [oldMethod,newMethod,label] of [['email','totp','totp'],['totp','email','emailFactor']]){
  const f=fixture('de',oldMethod);f.sandbox.setup(true);
  await control(f.views.at(-1),label).action();
  const view=f.views.at(-1);assert.equal(view.surface,'modal');
  assert(descendants(view.body).some(n=>n.key==='factorChangeIntro'));
  const code=control(view,'factorCode').children[0];code.value='bad';
  await assert.rejects(view.body.submit(),{code:'invalid_factor'});
  assert.equal(f.sandbox.state.user.factor,oldMethod);assert.equal(f.sandbox.state.csrf,'old-csrf');assert.equal(f.views.at(-1),view);
  code.value='123456';await view.body.submit();
  assert.equal(f.sandbox.state.user.factor,newMethod);assert.equal(f.sandbox.state.csrf,'new-csrf');assert.equal(code.value,'');
  assert.equal(f.requests.at(-1).body.method,newMethod);assert.equal(f.views.at(-1).title,'backupCodes');assert.equal(f.views.at(-1).surface,'modal');
 }
});

test('first enrollment stays on the sign-in screen without an escape to the application',async()=>{
 const f=fixture('en',null);f.sandbox.setup();
 assert.equal(f.views.at(-1).surface,'auth');assert.equal(f.views.at(-1).title,'factorTitle');
 assert(!descendants(f.views.at(-1).body).some(n=>n.label==='cancel'));
 await control(f.views.at(-1),'emailFactor').action();const view=f.views.at(-1);
 assert.equal(view.surface,'auth');control(view,'factorCode').children[0].value='123456';await view.body.submit();
 assert.equal(f.views.at(-1).surface,'auth');assert.equal(f.views.at(-1).title,'backupCodes');
});

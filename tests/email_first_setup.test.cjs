const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..'),source=fs.readFileSync(path.join(root,'mcj/static/app.js'),'utf8');
function fixture(language='de',canConfigure=true){
 const requests=[],views=[];
 function node(tag,props={},...children){return {tag,...props,children:children.flat(Infinity).filter(Boolean),append(...items){this.children.push(...items);},prepend(...items){this.children.unshift(...items);}};}
 const ctx={state:{language,user:{factor:null,email:'owner@example.test'},csrf:'pending-csrf'},node,
  button:(label,action)=>node('button',{label,action}),paragraph:key=>node('p',{key}),
  input:(type,value,props)=>node('input',{type,value,...props}),field:(label,child)=>node('label',{label},child),
  select:(options,value)=>node('select',{options,value}),form:(children,label,submit)=>node('form',{label,submit},children),
  modal:(title,body)=>views.push({title,body,surface:'modal'}),authBody:(title,body)=>views.push({title,body,surface:'auth'}),
  profile:()=>{},displayCodes:(codes,inModal)=>views.push({title:'backupCodes',codes,inModal}),
  api:async(url,body)=>{requests.push({url,body});
   if(url.endsWith('/status'))return {configured:false,can_configure:canConfigure};
   if(url.endsWith('/smtp')&&body.password==='wrong')throw {code:'smtp_authentication_failed'};
   if(url.endsWith('/confirm')){if(body.code==='000000')throw {code:'email_setup_code_invalid'};return {csrf:'confirmed-csrf',backup_codes:['disposable']};}
   return {challenge:'opaque-fixture',qr:'data:local',secret:'disposable-totp'};
  }};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'mcj/static/i18n.js'),'utf8')+'\nconst t=k=>TEXT[state.language][k]||k;'+source.slice(source.indexOf('function factorLabel('),source.indexOf('function downloadText('))+'\nthis.setup=factorSetup;this.messages=TEXT;',ctx);
 return {ctx,requests,views};
}
function all(n){return [n,...(n.children||[]).flatMap(all)];}
function control(view,label){const n=all(view.body).find(n=>n.label===label);assert(n,label);return n;}
function value(view,label,v){control(view,label).children[0].value=v;}
test('empty SMTP first sign-in offers configuration, confirms receipt and clears the password in DE and EN',async()=>{
 for(const language of ['de','en']){
  const f=fixture(language);f.ctx.setup();await control(f.views.at(-1),'emailFactor').action();
  const view=f.views.at(-1);assert.equal(view.title,'emailSetupTitle');assert.equal(view.surface,'auth');
  value(view,'emailSetupHost','smtp.example.test');value(view,'emailSetupUsername','owner');value(view,'emailSetupPassword','wrong');
  await assert.rejects(view.body.submit(),{code:'smtp_authentication_failed'});assert.equal(f.views.at(-1),view);
  assert.equal(control(view,'emailSetupPassword').children[0].value,'');assert.equal(f.ctx.state.user.factor,null);
  value(view,'emailSetupPassword','disposable');await view.body.submit();
  assert.equal(control(view,'emailSetupPassword').children[0].value,'');
  const confirmation=f.views.at(-1);assert.equal(confirmation.title,'emailFactor');
  value(confirmation,'factorCode','000000');await assert.rejects(confirmation.body.submit(),{code:'email_setup_code_invalid'});
  assert.equal(f.ctx.state.user.factor,null);assert.equal(f.ctx.state.csrf,'pending-csrf');
  value(confirmation,'factorCode','123456');await confirmation.body.submit();assert.equal(f.ctx.state.user.factor,'email');
  assert.equal(f.ctx.state.csrf,'confirmed-csrf');assert.equal(f.views.at(-1).title,'backupCodes');assert.equal(f.views.at(-1).inModal,false);
  assert.equal(f.requests.find(r=>r.url.endsWith('/smtp')).body.sender,'owner@example.test');
  for(const key of ['emailSetupTitle','emailSetupIntro','emailSetupCodeHelp','smtp_authentication_failed','email_setup_code_invalid']){
   assert(f.ctx.messages[language][key]);assert.notEqual(f.ctx.messages.de[key],f.ctx.messages.en[key]);
  }
 }
});
test('mail settings can be edited after sending without retaining the password; method selection stays available',async()=>{
 const f=fixture();f.ctx.setup();await control(f.views.at(-1),'emailFactor').action();const view=f.views.at(-1);
 value(view,'emailSetupHost','smtp.example.test');value(view,'emailSetupUsername','owner');value(view,'emailSetupPassword','disposable');await view.body.submit();
 await control(f.views.at(-1),'emailSetupEdit').action();assert.equal(f.views.at(-1).title,'emailSetupTitle');
 assert.equal(control(f.views.at(-1),'emailSetupPassword').children[0].value,'');assert.equal(control(f.views.at(-1),'emailSetupHost').children[0].value,'smtp.example.test');
 await control(f.views.at(-1),'back').action();await control(f.views.at(-1),'totp').action();assert.equal(f.views.at(-1).title,'totp');
 assert.equal(f.ctx.state.user.factor,null);assert.equal(f.requests.filter(r=>r.url.endsWith('/confirm')).length,0);
});
test('a non-administrator gets a readable choice instead of a password-only settings bypass',async()=>{
 const f=fixture('en',false);f.ctx.setup();await control(f.views.at(-1),'emailFactor').action();
 assert(all(f.views.at(-1).body).some(n=>n.key==='emailSetupAdminRequired'));
 assert(!all(f.views.at(-1).body).some(n=>n.label==='emailSetupSend'));
 await control(f.views.at(-1),'back').action();assert.equal(f.views.at(-1).title,'factorTitle');
});

// Browser-independent regression coverage for the real bootstrap script.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../mcj/static/bootstrap.js'),'utf8');
const starting={phase:'starting',progress:{completed:4,total:6},csrf:'fixture',parents:['/volume1/docker'],maximum_memory_mb:8192,recommended_memory_mb:6144,network:'192.168.1.0/24'};
const json=(value,ok=true)=>({ok,json:async()=>value});
async function fixture(i18n={text:key=>key,has:()=>true}){
 const elements=new Map(),timers=new Map(),requests=[],redirects=[];let timerId=0,now=1000;
 function element(id){if(!elements.has(id))elements.set(id,{hidden:true,options:[],attributes:new Set(['value']),value:'',textContent:'',classList:{toggle(){}},removeAttribute(name){this.attributes.delete(name);},replaceChildren(...children){this.options=children;},addEventListener(){}});return elements.get(id);}
 let route=async()=>json(starting);
 const context=vm.createContext({AbortController,Date:class extends Date{static now(){return now;}},SetupI18n:i18n,document:{getElementById:element,createElement:()=>({}),addEventListener(){}},location:{replace:value=>redirects.push(value)},fetch:(url,options)=>{requests.push({url,method:options.method||'GET'});return route(url,options);},setInterval(){},setTimeout:(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;},clearTimeout:id=>timers.delete(id)});
 vm.runInContext(script,context);await new Promise(setImmediate);
 return {elements,requests,redirects,timers,route:fn=>{route=fn;},advance:ms=>{now+=ms;},refresh:()=>vm.runInContext('refresh()',context)};
}
test('a missed handover tick and failed TLS do not leave a misleading 66% or claim success',async()=>{
 const f=await fixture();assert.equal(f.elements.get('setup-progress').value,4);
 f.route(async()=>{throw new TypeError('network unavailable');});await f.refresh();
 assert.equal(f.elements.get('setup-progress').attributes.has('value'),false);
 assert.equal(f.elements.get('progress-percent').textContent,'progressConnecting');
 assert.equal(f.elements.get('handover').hidden,false);assert.deepEqual(f.redirects,[]);
 f.advance(31000);await f.refresh();assert.equal(f.elements.get('message').textContent,'error.manager_delayed');
 assert.equal(f.requests.some(r=>r.method!=='GET'),false);assert.equal(f.timers.size,0);
 f.route(async()=>json(starting));await f.refresh();assert.equal(f.elements.get('message').textContent,'');assert.equal(f.elements.get('setup-progress').value,4);
});
test('the manager is opened only after a successful health response',async()=>{
 const f=await fixture();f.route(async url=>url==='/healthz'?json({version:'1.0.0',state:'internal_validation'}):json({detail:'Not Found'},false));
 await f.refresh();assert.deepEqual(f.redirects,['/']);assert.equal(f.timers.size,0);
});
test('an HTTP error or malformed health body cannot be mistaken for completion',async()=>{
 for(const response of [json({version:'1.0.0',state:'ready'},false),json({version:'1.0.0'}),json({detail:'external_web_disabled'},false)]){
  const f=await fixture();f.route(async url=>url==='/healthz'?response:json({detail:'Not Found'},false));await f.refresh();assert.deepEqual(f.redirects,[]);
 }
});
test('a stalled request is bounded and overlapping polls are suppressed',async()=>{
 const f=await fixture();let calls=0;
 f.route((url,options)=>{
  calls++;return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}));
 });
 const active=f.refresh();await f.refresh();assert.equal(calls,1);
 const stateTimeout=[...f.timers.values()].find(t=>t.ms===8000);assert.ok(stateTimeout);stateTimeout.fn();await new Promise(setImmediate);
 const healthTimeout=[...f.timers.values()].find(t=>t.ms===5000);assert.ok(healthTimeout);healthTimeout.fn();await active;
 assert.equal(calls,2);assert.equal(f.timers.size,0);assert.equal(f.elements.get('handover').hidden,false);
 f.route(async()=>json(starting));await f.refresh();assert.equal(f.elements.get('message')?.textContent||'','');assert.equal(f.elements.get('setup-progress').value,4);
});

test('reported setup failures explain the cause in both languages without reflecting unknown worker text',async()=>{
 let changeLanguage;const languageSelect={value:'de',addEventListener:(name,callback)=>{changeLanguage=callback;}};
 const translations=vm.createContext({window:{},localStorage:{getItem:()=> 'de',setItem(){}},Event:class{},document:{body:{dataset:{}},documentElement:{},getElementById:()=>languageSelect,querySelectorAll:()=>[],dispatchEvent(){}}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../mcj/static/bootstrap-i18n.js'),'utf8'),translations);
 const i18n=translations.window.SetupI18n,f=await fixture(i18n);
 f.route(async()=>json({...starting,phase:'failed',error:'setup_port_in_use'}));await f.refresh();
 assert.equal(f.elements.get('phase').textContent,i18n.text('phase.failed')+' '+i18n.text('error.setup_port_in_use'));
 assert.match(f.elements.get('phase').textContent,/Anschluss/);
 changeLanguage({target:{value:'en'}});await f.refresh();assert.match(f.elements.get('phase').textContent,/port/);assert.doesNotMatch(f.elements.get('phase').textContent,/Anschluss/);
 const privateDetail='UNKNOWN_WORKER_MESSAGE /private/path TOKEN=never_display_this';
 f.route(async()=>json({...starting,phase:'failed',error:privateDetail}));await f.refresh();
 assert.equal(f.elements.get('phase').textContent,i18n.text('phase.failed'));assert(!f.elements.get('phase').textContent.includes(privateDetail));
 f.route(async()=>json({...starting,error:'setup_port_in_use'}));await f.refresh();
 assert.equal(f.elements.get('phase').textContent,i18n.text('phase.starting'));
 assert.equal(f.requests.some(r=>r.method!=='GET'),false);
});

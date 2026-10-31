'use strict';
const el=id=>document.getElementById(id),t=(key,values)=>SetupI18n.text(key,values);
let csrf='',busy=false,lastState=null,lastError=null,connectingSince=0,refreshing=false;
const setupStages=['checking','folders','runtime','account','starting','handover','complete'];
function setupError(code){const error=new Error(code);error.code=code;return error;}
function errorText(error){const key='error.'+(error.code||'generic');return t(SetupI18n.has(key)?key:'error.generic');}
function showError(error){lastError=error;el('message').textContent=error?errorText(error):'';}
async function api(path,value){
 let response,result;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
 try{response=await fetch(path,{method:value?'POST':'GET',headers:value?{'Content-Type':'application/json','X-CSRF':csrf}:{},body:value?JSON.stringify(value):undefined,cache:'no-store',signal:controller.signal});result=await response.json();}
 catch{throw setupError('generic');}finally{clearTimeout(timer);}
 if(!response.ok)throw setupError(result.error||'generic');return result;
}
function choices(target,values){target.replaceChildren(...values.map(([value,text])=>{const option=document.createElement('option');option.value=value;option.textContent=text;return option;}));}
function renderStatus(){
 if(lastError)el('message').textContent=errorText(lastError);
 if(!lastState)return;
 const reported=lastState.progress?.completed,done=Number.isInteger(reported)&&reported>=0&&reported<=6?reported:Math.max(0,setupStages.indexOf(lastState.phase));
 if(connectingSince){el('setup-progress').removeAttribute('value');el('progress-percent').textContent=t('progressConnecting');}
 else{el('setup-progress').value=done;el('progress-percent').textContent=t('progressCount',{completed:done,total:6,percent:Math.floor(done/6*100)});}
 const key=connectingSince?'phase.connecting':'phase.'+lastState.phase;
 const phaseText=t(SetupI18n.has(key)?key:'phase.pending');
 const failureKey='error.'+lastState.error;
 el('phase').textContent=phaseText+(lastState.phase==='failed'&&SetupI18n.has(failureKey)?' '+t(failureKey):'');
 el('setup-progress').classList.toggle('is-failed',lastState.phase==='failed');
 el('memory-help').textContent=t('recommendation',{memory:lastState.recommended_memory_mb/1024,network:lastState.network});
}
async function managerReady(){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
 try{const response=await fetch('/healthz',{cache:'no-store',signal:controller.signal});if(!response.ok)return false;const value=await response.json();return typeof value.version==='string'&&typeof value.state==='string';}catch{return false;}finally{clearTimeout(timer);}
}
async function refresh(){
 if(refreshing)return;refreshing=true;
 try{
  const state=await api('/setup/state');lastState=state;csrf=state.csrf;el('unlock').hidden=true;connectingSince=0;
  if(lastError?.poll)showError(null);
  const running=!['ready','failed'].includes(state.phase);
  el('selection').hidden=running;el('progress').hidden=!running&&state.phase!=='failed';
  el('handover').hidden=!['handover','complete'].includes(state.phase);
  if(!busy&&!el('parent').options.length){
   choices(el('parent'),state.parents.map((text,index)=>[index,text]));choices(el('backup-parent'),state.parents.map((text,index)=>[index,text]));
   choices(el('memory'),Array.from({length:state.maximum_memory_mb/1024-3},(_,i)=>[(i+4)*1024,(i+4)+' GiB']));el('memory').value=state.recommended_memory_mb;
  }
  renderStatus();
 }catch(error){
  if(lastState&&!['ready','failed'].includes(lastState.phase)){
   // The setup listener disappears before the manager binds the same HTTPS port.
   // A polling tick may miss the very short handover phase entirely.
   if(await managerReady()){location.replace('/');return;}
   if(error.code==='generic'){
    connectingSince=connectingSince||Date.now();el('handover').hidden=false;
    if(Date.now()-connectingSince>30000){const delayed=setupError('manager_delayed');delayed.poll=true;showError(delayed);}
    renderStatus();
    return;
   }
  }
  if(error.code==='authentication_required'){
   el('unlock').hidden=false;el('selection').hidden=true;el('progress').hidden=true;
   if(lastState)showError(error);
  }else{error.poll=true;showError(error);}
 }finally{refreshing=false;}
}
document.addEventListener('setup-language-change',renderStatus);
el('unlock-form').addEventListener('submit',async event=>{
 event.preventDefault();try{const result=await api('/setup/unlock',{code:el('code').value.trim()});el('code').value='';csrf=result.csrf;showError(null);await refresh();}catch(error){showError(error);}
});
el('install-form').addEventListener('submit',async event=>{
 event.preventDefault();if(busy)return;
 if(el('password').value!==el('repeat').value){showError(setupError('password_mismatch'));return;}
 busy=true;el('start').disabled=true;
 try{
  await api('/setup/install',{parent:Number(el('parent').value),backup_parent:Number(el('backup-parent').value),folder:el('folder').value,backup_folder:el('backup-folder').value,username:el('username').value,email:el('email').value,password:el('password').value,access_mode:el('access').value,memory_mb:Number(el('memory').value),accept_eula:el('eula').checked});
  el('password').value='';el('repeat').value='';showError(null);el('selection').hidden=true;el('progress').hidden=false;
 }catch(error){showError(error);}finally{busy=false;el('start').disabled=false;await refresh();}
});
refresh();setInterval(refresh,3000);

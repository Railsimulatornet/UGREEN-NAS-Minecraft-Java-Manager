'use strict';
let pendingSettingsChanges=null,pendingModChanges=[];
let state={csrf:null,user:null,page:'overview',language:localStorage.getItem('mcj-language')||'de',challenge:'',recovery:false,modSearch:'',modFilter:'all'};
if(!TEXT[state.language])state.language='de';
const $=id=>document.getElementById(id);
const t=key=>TEXT[state.language][key]||key;
const errorText=code=>TEXT[state.language][code]||t('unexpectedError');
const errorParagraph=(code,style='')=>node('p',{class:style,text:errorText(code)});
function displayText(value){if(value===null||value===undefined)return '';if(typeof value==='number')return Number.isFinite(value)?String(value):'—';if(typeof value==='string')return ['null','undefined','[object Object]','NaN'].includes(value.trim())?t('unknown'):value;if(typeof value==='boolean')return String(value);return t('unknown');}
function node(tag,props={},...children){const element=document.createElement(tag);for(const [key,value] of Object.entries(props)){if(key==='class')element.className=value;else if(key==='text')element.textContent=displayText(value);else if(key.startsWith('on'))element.addEventListener(key.slice(2),value);else if(key in element)element[key]=value;else element.setAttribute(key,value);}for(const child of children.flat(Infinity)){if(child!==null&&child!==undefined)element.append(child instanceof Node?child:document.createTextNode(displayText(child)));}return element;}
// Local vector icons: no external requests, fonts or executable SVG markup.
const ICONS={overview:['M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z'],mods:['M12 3 3 7.5v9L12 21l9-4.5v-9L12 3Z M3 7.5l9 4.5 9-4.5 M12 12v9'],backups:['M4 7h16v14H4z M3 3h18v4H3z M9 11h6 M12 11v6 M9 14l3 3 3-3'],events:['M5 3h14v18H5z M8 7h8 M8 11h8 M8 15h5'],server:['M4 3h16v7H4z M4 14h16v7H4z M7 6.5h.01 M7 17.5h.01 M11 6.5h6 M11 17.5h6'],playersOnline:['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M20 21v-2a4 4 0 0 0-3-3.87 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M16 3.13a4 4 0 0 1 0 7.75'],cpu:['M6 6h12v12H6z M9 9h6v6H9z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M2 15h4 M18 9h4 M18 15h4'],memory:['M3 6h18v12H3z M7 10v4 M11 10v4 M15 10v4 M19 10v4 M6 18v3 M10 18v3 M14 18v3 M18 18v3'],tps:['M3 12h4l3-8 4 16 3-8h4'],disk:['M4 4h16v16H4z M4 15h16 M7 18h.01 M10 18h.01'],uptime:['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l3 2'],refresh:['M20 7v5h-5 M4 17v-5h5 M6 7a7 7 0 0 1 12-2l2 2 M4 17l2 2a7 7 0 0 0 12-2'],start:['m8 5 11 7-11 7V5Z'],stop:['M5 5h14v14H5z'],settings:['M9 3h6l1 4 4 1v8l-4 1-1 4H9l-1-4-4-1V8l4-1 1-4Z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6'],shield:['m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z m-4 9 3 3 5-6']};
const ITEM_ICONS={brand:'creeper',server:'grass',backups:'chest',disk:'chest',cpu:'furnace',memory:'crafting',tps:'redstone',uptime:'clock',playersOnline:'player'};
ICONS.overview=['m3 11 9-8 9 8 M5 10v11h5v-7h4v7h5V10'];
const ASSET_ICONS={brand:'branding/server_logo.png',memory:'symbols/crafting_table.png',overview:'symbols/overview.svg',mods:'symbols/mods.svg',backups:'symbols/backups.png',events:'symbols/events.svg',server:'symbols/server.png',playersOnline:'symbols/players.svg',cpu:'cpu/furnace_00_unknown.png',tps:'tps/redstone_00_unknown.png',disk:'storage/chest_00_unknown.png',uptime:'clock/clock_dial_no_hands.png',settings:'symbols/settings.svg',refresh:'symbols/update.svg',start:'symbols/start.svg',stop:'symbols/stop.svg',terminal:'symbols/console.svg',mail:'symbols/mail.svg',worlds:'symbols/worlds.svg',players:'symbols/players.svg',discord:'symbols/discord.svg'};
function icon(name){
 if(ASSET_ICONS[name])return node('img',{class:'ui-icon icon-asset icon-'+name,src:'/static/assets/final/'+ASSET_ICONS[name],alt:'',decoding:'async',width:64,height:64,'aria-hidden':'true'});
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');for(const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.65','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true',focusable:'false',class:'ui-icon'}))svg.setAttribute(key,value);for(const d of ICONS[name]||ICONS.overview){const path=document.createElementNS(ns,'path');path.setAttribute('d',d);svg.append(path);}return svg;
}
ICONS.terminal=['M3 4h18v16H3Z m4 5 3 3-3 3 m6 1h4'];
ICONS.wrench=['M21 3a6 6 0 0 1-7 8L7 20a2 2 0 0 1-3-3l9-7a6 6 0 0 1 8-7l-4 4 1 2 2 1 4-4'];
function decoratePanelHeaders(){for(const [selector,name] of [['.players-card','server'],['.console-card','terminal'],['.maintenance-card','wrench']]){const title=document.querySelector(selector+' .card-head h3');if(title&&!title.querySelector('.ui-icon'))title.prepend(icon(name));}}
const ACTION_ICONS={refresh:'refresh',start:'start',restart:'refresh',stop:'stop',backupNow:'backups',installMods:'mods',checkUpdates:'refresh'};
const button=(label,action,cls='')=>node('button',{type:'button',class:cls+(label==='start'?' action-start':label==='restart'?' action-restart':''),onclick:event=>{const target=event.currentTarget;if(target.disabled)return;target.disabled=true;attempt(async()=>{try{await action();}finally{target.disabled=false;}});}},ACTION_ICONS[label]?icon(ACTION_ICONS[label]):null,node('span',{text:t(label)}));
const paragraph=(key,cls='')=>node('p',{class:cls,text:t(key)});
function field(label,input){return node('label',{class:'field'},node('span',{text:t(label)}),input);}
function input(type='text',value='',props={}){return node('input',{type,value,...props});}
function select(options,value){return node('select',{},options.map(([key,label])=>node('option',{value:key,text:t(label),selected:String(key)===String(value)})));}
function toast(message,tone='info'){const target=$('modal')?.open?$('modal'):document.body;if($('toast').parentElement!==target)target.append($('toast'));$('toast').textContent=message;$('toast').classList.toggle('is-error',tone==='error');$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,6000);}
function translate(){document.documentElement.lang=state.language;document.querySelectorAll('[data-i18n-aria]').forEach(element=>element.setAttribute('aria-label',t(element.dataset.i18nAria)));document.querySelectorAll('[data-i18n]').forEach(element=>element.textContent=t(element.dataset.i18n));$('language').value=state.language;}
let settingsDraftState=null,settingsReturnView=null,unsavedDialogView=null;
function modal(title,body,options={}){
 const show=()=>{if(!options.preserveSettings){clearSettingsDraft();settingsReturnView=null;}else if(settingsDraftState?.root.isConnected)settingsReturnView=dialogView();$('modal').classList.remove('settings-dialog');$('modal-title').textContent=t(title);$('modal-content').replaceChildren(body);if(!$('modal').open)$('modal').showModal();$('modal').scrollTop=0;
  if(options.trackDraft)trackSettingsDraft(body);
  if(title==='settings'){$('modal').classList.add('settings-dialog');trackSettingsDraft(body);if(body.dataset.initialFocus==='localRuntimeFiles')body.querySelector('#local-runtime-files')?.scrollIntoView({block:'start'});}
  options.onShow?.();
 };
 if(!options.preserveSettings&&settingsDraftDirty()){requestUnsavedDecision(show);return;}show();
}
function closeModal(force=false){
 if(force!==true){if(unsavedDialogView){continueSettingsEditing();return;}if(settingsReturnView){restoreSettingsReturn();return;}if(settingsDraftDirty()){requestUnsavedDecision(()=>closeModal(true));return;}}
 unsavedDialogView=null;settingsReturnView=null;clearSettingsDraft();$('modal').close();$('modal-content').replaceChildren();queueMicrotask(()=>attempt(refreshVisiblePage));
}
async function attempt(action){try{await action();}catch(error){if(error.code==='authentication_required'){closeModal();loginScreen();}toast(errorText(error.code),'error');}}
async function api(path,body,method){const options={method:method||(body===undefined?'GET':'POST'),credentials:'same-origin',headers:{}};if(body!==undefined){if(body instanceof FormData)options.body=body;else if(body instanceof Blob){options.headers['Content-Type']='application/zip';options.body=body;}else{options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}if(state.csrf)options.headers['X-CSRF-Token']=state.csrf;}const response=await fetch('/api'+path,options);let result;try{result=await response.json();}catch{result={};}if(!response.ok){const error=new Error('Request failed');error.code=typeof result.detail==='string'?result.detail:'error';throw error;}if(body!==undefined&&path.startsWith('/jobs')){globalJobsChecked=0;attempt(refreshGlobalJobs);}return result;}
function form(body,submitLabel,action){const element=node('form',{class:'form-grid'},body);const submit=node('button',{type:'submit',class:'primary',text:t(submitLabel)});element.append(submit);element.addEventListener('submit',event=>{event.preventDefault();if(submit.disabled)return;attempt(async()=>{submit.disabled=true;try{await action();if(element.isConnected&&['smtp','providers','discord','schedules','minecraftPermissions','greetings'].includes(element.closest('.settings-panel')?.dataset.settingsCategory))markSettingsFormSaved(element);}finally{submit.disabled=false;}});});return element;}
function authBody(title,body){document.body.dataset.authenticated='false';$('authentication').hidden=false;$('application').hidden=true;$('settings-button').hidden=true;$('profile-button').hidden=true;$('auth-content').replaceChildren(node('h2',{text:t(title)}),body);}
function loginScreen(){closeModal(true);pendingSettingsChanges=null;pendingModChanges=[];updateChangeBasket();state.user=null;const username=input('text','',{required:true,autocomplete:'username',maxLength:80});const password=input('password','',{required:true,autocomplete:'current-password',maxLength:128});const content=form([field('username',username),field('password',password)],'login',async()=>{const response=await api('/auth/login',{username:username.value,password:password.value});password.value='';state.csrf=response.csrf;state.challenge=response.challenge||'';state.emailDeliveryError=response.email_delivery_error||'';await continueAuthentication();});content.append(button('forgot',forgotScreen,'text-button'));authBody('login',content);}
async function continueAuthentication(){const result=await api('/auth/me');state.user=result.user;state.csrf=result.csrf;state.language=state.user.language;localStorage.setItem('mcj-language',state.language);translate();if(state.user.force_password){passwordScreen(true);return;}if(!state.user.factor){factorSetup();return;}if(!result.mfa_verified){await verifyScreen();return;}showApplication();if(result.setup_wizard_pending)attempt(()=>setupWizard());}
function passwordScreen(first=false){const current=input('password','',{required:true,autocomplete:'current-password',maxLength:128});const password=input('password','',{required:true,autocomplete:'new-password',minLength:12,maxLength:128});const repeat=input('password','',{required:true,autocomplete:'new-password',minLength:12,maxLength:128});const content=form([first?paragraph('firstPassword'):null,field('currentPassword',current),field('newPassword',password),field('repeatPassword',repeat)],'changePassword',async()=>{if(password.value!==repeat.value){toast(t('passwordMismatch'));return;}const response=await api('/auth/password',{current:current.value,password:password.value});current.value='';password.value='';repeat.value='';state.csrf=response.csrf;if(first)await continueAuthentication();else{closeModal();toast(t('saved'));}});if(first)authBody('changePassword',content);else modal('changePassword',content);}
function factorLabel(){return t(state.user.factor==='totp'?'totp':state.user.factor==='email'?'emailFactor':'unknown');}
function factorPanel(){return node('section',{class:'stack'},node('h3',{text:t('accountFactor')}),node('p',{text:t('activeFactor')+': '+factorLabel()}),paragraph('factorIntro','hint'),button('changeFactor',()=>factorSetup(true)));}
function factorSetup(changing=false){
 const show=(title,content)=>{
  if(changing){content.prepend(paragraph('factorChangeIntro','hint'));content.append(button('cancel',profile));modal(title,content);}
  else authBody(title,content);
 };
 const confirm=async(method,setup,code)=>{
  const result=await api('/auth/setup/confirm',{method,challenge:setup.challenge,code:code.value});
  code.value='';state.csrf=result.csrf;state.user.factor=method;
  displayCodes(result.backup_codes,changing);
 };
 const emailConfirmation=(setup,edit)=>{
  const code=input('text','',{required:true,autocomplete:'one-time-code',inputMode:'numeric',pattern:'[0-9]{6}',maxLength:6});
  const content=form([paragraph('emailSetupCodeHelp'),field('factorCode',code)],'verify',()=>confirm('email',setup,code));
  content.append(button(edit?'emailSetupEdit':'back',edit||(()=>factorSetup(changing))));
  show('emailFactor',content);
 };
 const configureMail=(previous={})=>{
  const host=input('text',previous.host||'',{required:true,maxLength:253,autocomplete:'off'});
  const port=input('number',previous.port||587,{required:true,min:1,max:65535});
  const security=select([['starttls','STARTTLS'],['tls','TLS']],previous.security||'starttls');
  const username=input('text',previous.username||'',{required:true,maxLength:254,autocomplete:'off'});
  const sender=input('email',previous.sender||state.user.email,{required:true,maxLength:254});
  const password=input('password','',{required:true,maxLength:1000,autocomplete:'off'});
  const content=form([paragraph('emailSetupIntro'),paragraph('emailSetupTransportHelp','hint'),
   field('emailSetupHost',host),field('port',port),field('security',security),field('emailSetupUsername',username),field('emailSetupSender',sender),field('emailSetupPassword',password)],'emailSetupSend',async()=>{
    const settings={host:host.value.trim(),port:Number(port.value),security:security.value,username:username.value,sender:sender.value.trim()};
    let setup;try{setup=await api('/auth/setup/email/smtp',{...settings,password:password.value});}finally{password.value='';}
    emailConfirmation(setup,()=>configureMail(settings));
   });
  content.append(button('back',()=>factorSetup(changing)));
  show('emailSetupTitle',content);
 };
 const body=node('div',{class:'stack'},paragraph('factorIntro'),button('totp',async()=>{
  const setup=await api('/auth/setup/totp',{});
  const code=input('text','',{required:true,autocomplete:'one-time-code',inputMode:'numeric',maxLength:6});
  const content=form([paragraph('totpScanHelp'),node('img',{class:'totp-qr',src:setup.qr,alt:t('totpQrAlt'),width:256,height:256}),node('details',{},node('summary',{text:t('totpManual')}),paragraph('totpSetup'),node('div',{class:'secret',text:setup.secret}),button('totpCopyKey',async()=>{await navigator.clipboard.writeText(setup.secret);toast(t('copied'));})),field('factorCode',code)],'verify',()=>confirm('totp',setup,code));
  content.append(button('back',()=>factorSetup(changing)));
  show('totp',content);
 }),button('emailFactor',async()=>{
  const status=await api('/auth/setup/email/status');
  if(!status.configured){
   if(status.can_configure)configureMail();
   else show('emailFactor',node('div',{class:'stack'},paragraph('emailSetupAdminRequired'),button('back',()=>factorSetup(changing))));
   return;
  }
  emailConfirmation(await api('/auth/setup/email',{}));
 }));
 show(changing?'changeFactor':'factorTitle',body);
}
function downloadText(filename,text){const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const link=node('a',{href:url,download:filename});document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function displayCodes(codes,inModal=false){const body=node('div',{},paragraph('codesIntro'),node('div',{class:'backup-codes'},codes.map(code=>node('span',{text:code}))),node('div',{class:'form-actions'},button('downloadCodes',()=>downloadText('minecraft-backup-codes.txt',codes.join('\n')+'\n')),button('codesSaved',async()=>{codes.fill('');if(inModal)closeModal();else await continueAuthentication();},'primary')));if(inModal)modal('backupCodes',body);else authBody('backupCodes',body);}
async function verifyScreen(){const remember=select([['0','rememberDefault'],['7','remember7'],['14','remember14'],['30','remember30']],'0');const code=input('text','',{required:true,autocomplete:'one-time-code',maxLength:100});const recovery=input('checkbox');let challenge=state.challenge;const body=form([node('p',{text:t('activeFactor')+': '+factorLabel()}),field('factorCode',code),node('label',{class:'checkbox-field'},recovery,t('useRecovery')),field('rememberDevice',remember),paragraph('rememberDeviceHint','hint')],'verify',async()=>{const response=await api('/auth/verify',{code:code.value,challenge,recovery:recovery.checked,remember_days:Number(remember.value)});code.value='';state.csrf=response.csrf;await continueAuthentication();});if(state.user.factor==='email'){const sent=state.emailDeliveryError?errorParagraph(state.emailDeliveryError,'error'):paragraph(challenge?'loginCodeSent':'emailLoginCodeNeeded');let resend;const pause=()=>{resend.disabled=true;setTimeout(()=>{if(resend.isConnected)resend.disabled=false;},60000);};resend=button('resendCode',async()=>{pause();const result=await api('/auth/email-challenge',{});challenge=result.challenge;state.challenge=challenge;state.emailDeliveryError='';sent.textContent=t('loginCodeSent');sent.className='';toast(t('emailCodeSent'));});body.insertBefore(resend,body.firstChild);body.insertBefore(sent,body.firstChild);if(challenge)pause();}authBody('verify',body);}
function forgotScreen(){const email=input('email','',{required:true,autocomplete:'email',maxLength:254});const body=form([field('email',email)],'reset',async()=>{await api('/auth/forgot',{email:email.value});authBody('reset',node('div',{},paragraph('resetSent'),button('back',loginScreen)));});body.append(button('back',loginScreen,'text-button'));authBody('reset',body);}
let resetScreenGeneration=0;
async function resetScreen(token){
 const generation=++resetScreenGeneration;authBody('reset',paragraph('resetLinkChecking'));
 let context;
 try{context=await api('/auth/reset/context',{token});}
 catch(error){if(generation!==resetScreenGeneration)return;authBody('reset',node('div',{},errorParagraph(error.code),button('requestNewResetLink',forgotScreen)));return;}
 if(generation!==resetScreenGeneration)return;
 const password=input('password','',{required:true,minLength:12,maxLength:128,autocomplete:'new-password'});
 const code=input('text','',{required:!!context.factor,autocomplete:'one-time-code',maxLength:100});
 const recovery=input('checkbox');let challenge='';
 const controls=[node('p',{text:t('resetForAccount')+' '+context.username}),paragraph(context.initial_setup?'initialResetHint':'configuredResetHint','hint'),field('newPassword',password)];
 if(context.factor){
  controls.push(field('factorCode',code),node('label',{class:'checkbox-field'},recovery,t('useRecovery')));
  if(context.factor==='email'){
   const send=button('sendCode',async()=>{if(!password.reportValidity())return;const response=await api('/auth/reset/email-challenge',{token,password:password.value});challenge=response.challenge;toast(t('emailCodeSent'));});
   recovery.addEventListener('change',()=>send.hidden=recovery.checked);controls.push(send);
  }
 }
 const body=form(controls,'reset',async()=>{
  await api('/auth/reset',{token,password:password.value,code:context.factor?code.value:'',challenge,recovery:!!context.factor&&recovery.checked});
  password.value='';code.value='';token='';toast(t('saved'));loginScreen();
 });authBody('reset',body);
}
function updateEventAccess(){document.querySelector('[data-page="events"]').hidden=!state.user.admin;if(!state.user.admin){state.eventView=null;if(state.page==='events'){state.page='overview';$('page-content').replaceChildren();}}}
function showApplication(){document.body.dataset.authenticated='true';$('authentication').hidden=true;$('application').hidden=false;$('settings-button').hidden=!state.user.admin;$('profile-button').hidden=false;$('profile-button').textContent=state.user.username.slice(0,1).toUpperCase();$('setup-assistant').hidden=true;updateEventAccess();renderPage();}
function date(value){if(!value)return '—';const d=typeof value==='number'?new Date(value*1000):new Date(value);if(!Number.isFinite(d.getTime()))return '—';return new Intl.DateTimeFormat(state.language==='de'?'de-DE':'en-GB',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',timeZoneName:'short',timeZone:'Europe/Berlin'}).format(d);}
function bytes(value){if(typeof value!=='number'||!Number.isFinite(value)||value<0)return '—';let index=0;const units=['B','KiB','MiB','GiB','TiB'];while(value>=1024&&index<4){value/=1024;index++;}return value.toLocaleString(state.language,{maximumFractionDigits:index?1:0})+' '+units[index];}
function decimal(value){return typeof value==='number'&&Number.isFinite(value)?value.toLocaleString(state.language,{minimumFractionDigits:1,maximumFractionDigits:1}):'—';}
function duration(value){if(typeof value!=='number'||!Number.isFinite(value)||value<0)return '—';value=Math.max(0,Math.floor(value));return value>=86400?Math.floor(value/86400)+'d '+Math.floor(value%86400/3600)+'h':Math.floor(value/3600)+'h '+Math.floor(value%3600/60)+'m';}
function jobDuration(value){if(typeof value!=='number'||!Number.isFinite(value)||value<0)return '—';const seconds=Math.floor(value);return seconds<60?seconds+'s':seconds<3600?Math.floor(seconds/60)+'m '+seconds%60+'s':duration(seconds);}
function pill(label,style=''){return node('span',{class:'pill '+style,text:TEXT[state.language][label]||t('unknown')});}
function heading(title,subtitle,actions=[]){return node('div',{class:'page-heading'},node('div',{},node('h1',{text:t(title)}),paragraph(subtitle)),node('div',{class:'actions'},actions));}
function table(headers,rows,empty){return node('div',{class:'table-wrap'},rows.length?node('table',{class:'responsive-table',role:'table'},node('thead',{role:'rowgroup'},node('tr',{role:'row'},headers.map(x=>node('th',{scope:'col',role:'columnheader',text:t(x)})))),node('tbody',{role:'rowgroup'},rows.map(row=>node('tr',{role:'row'},row.map((cell,index)=>node('td',{role:'cell','data-label':t(headers[index]),class:headers[index]==='actions'?'table-actions-cell':''},cell)))))):node('div',{class:'empty',text:t(empty)}));}
function metric(label,value,unit='',hint=''){const status=label==='server'?(value===t('running')?'online':value===t('unknown')?'unknown':'offline'):'';return node('section',{class:'card metric metric-'+label+(status?' metric-'+status:'')},node('div',{class:'metric-label'},['cpu','disk','tps','uptime','playersOnline'].includes(label)?node('span',{class:'ui-icon','aria-hidden':'true'}):(document.querySelector('.metric-'+label+' .metric-label>.icon-asset')||icon(label)),node('span',{text:t(label)})),node('div',{class:'metric-value'},status?node('span',{class:'server-state-dot'}):null,String(value??'—'),unit?node('small',{text:unit}):null),hint?node('div',{class:'metric-footnote',text:hint}):null);}
async function queue(kind,payload={},mode='manual'){await api('/jobs',{kind,payload,mode,approved:true});toast(t('jobQueued'));await renderPage();if(['restore_test','version_test'].includes(kind))await openMaintenance();}
// Decorative status graphics use the same observations as the numeric cards.
let metricAnimations=[];
const svgNode=(tag,attrs={},...children)=>{const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));for(const child of children)el.append(child);return el;};
function metricVisualState(status,now=Date.now()){
 const valid=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0;
 const reading=Object.hasOwn(status,'cpu_normalized_percent')?status.cpu_normalized_percent:status.cpu_percent;
 const cpu=valid(reading)&&reading<=100?reading:null;
 const disk=status.disk,used=disk&&valid(disk.total)&&disk.total>0&&valid(disk.free)&&disk.free<=disk.total?(disk.total-disk.free)/disk.total*100:null;
 const quality=valid(status.tps)&&status.tps<=20&&valid(status.mspt)?Math.min(1,status.tps/20,status.mspt>0?40/status.mspt:1):null;
 const qualityBand=quality===null?'unknown':status.tps<15||status.mspt>50?'critical':status.tps<19||status.mspt>=40?'warning':'good';
 const qualityArtworkState=quality===null?'unknown':status.tps<15||status.mspt>50?'dark':status.tps<18||status.mspt>=45?'weak':status.tps<19||status.mspt>=40?'medium':'bright';
 const cpuBand=cpu===null?'unknown':cpu<=15?'cold':cpu<=50?'weak':cpu<=85?'burning':'strong';
 const storageBand=used===null?'unknown':used<=25?'empty':used<=50?'partial':used<=75?'filled':'full';
 const players=Number.isSafeInteger(status.players_online)&&status.players_online>=0?status.players_online:null;
 const started=Date.parse(status.started_at),elapsed=status.container_status==='running'&&Number.isFinite(started)&&started<=now?(now-started)/1000:null;
 return {cpu,cpuBand,used,storageBand,quality,qualityBand,qualityArtworkState,players,visiblePlayers:players===null?0:Math.min(3,players),elapsed,started:elapsed===null?null:started};
}
function stopMetricEffects(){for(const entry of metricAnimations)entry.animation.cancel();metricAnimations=[];}
function updateUptimeGraphic(clock){
 const start=Number(clock.dataset.started);if(!Number.isFinite(start))return;
 const seconds=Math.max(0,(Date.now()-start)/1000);
 const pivotX=DESIGN_ASSETS.clock.layer_pivot_px[0],pivotY=DESIGN_ASSETS.clock.layer_pivot_px[1];clock.querySelector('.clock-hour').setAttribute('transform','rotate('+(seconds%43200/43200*360)+' '+pivotX+' '+pivotY+')');
 clock.querySelector('.clock-minute').setAttribute('transform','rotate('+(seconds%3600/3600*360)+' '+pivotX+' '+pivotY+')');
 const value=clock.closest('.metric').querySelector('.metric-value');if(value.firstChild?.nodeType===Node.TEXT_NODE&&value.firstChild.nodeValue!==duration(seconds))value.firstChild.nodeValue=duration(seconds);
}
// Use only the user's 1.2 file family; no reconstructed sprite variants.
const FINAL_DESIGN_ASSETS={
 furnace:Object.fromEntries(['cold','weak','burning','strong','unknown'].map((key,i)=>[key,i===4?DESIGN_ASSETS.cpu.unknown:DESIGN_ASSETS.cpu.states[i].file])),
 chest:Object.fromEntries(['empty','partial','filled','full','unknown'].map((key,i)=>[key,i===4?DESIGN_ASSETS.storage.unknown:DESIGN_ASSETS.storage.states[i].file])),
 redstone:DESIGN_ASSETS.tps_mspt.states,
 clock:{face:DESIGN_ASSETS.clock.dial,hour:DESIGN_ASSETS.clock.hour_hand,minute:DESIGN_ASSETS.clock.minute_hand,pivot:DESIGN_ASSETS.clock.pivot_cap},players:DESIGN_ASSETS.players.avatars
};
function originalAsset(name){return typeof name==='string'&&/^[A-Za-z0-9_./-]+\.(png|webp|svg)$/.test(name)&&!name.split('/').some(x=>x==='..'||x==='.')?'/static/assets/final/'+name:null;}
function stateGraphic(target,file){
 if(target.tagName==='IMG'){const replacement=node('span');target.replaceWith(replacement);target=replacement;}
 const role=Array.from(target.closest('.metric').classList).find(x=>x.startsWith('metric-'));
 const previous=document.querySelector('.'+role+' .reference-state-art>img:not(.state-previous)');
 const src=originalAsset(file);if(src&&target.classList.contains('reference-state-art')&&target.querySelector('img:not(.state-previous)')?.getAttribute('src')===src)return;
 target.className='ui-icon status-visual reference-state-art';target.replaceChildren();
 target.dataset.artwork=src?'original':'missing';
 if(!src){target.append(node('span',{class:'reference-art-missing',text:t('originalArtworkMissing')}));return;}
 if(previous&&previous.getAttribute('src')===src){previous.classList.remove('state-entering');target.append(previous);return;}
 const current=node('img',{src,alt:'',decoding:'async',width:100,height:100});
 if(previous&&!matchMedia('(prefers-reduced-motion: reduce)').matches){previous.className='state-previous';target.append(previous);current.className='art-loading';const ready=()=>{current.className='state-entering';setTimeout(()=>previous.remove(),500);};current.addEventListener('load',ready,{once:true});if(current.complete&&current.naturalWidth)ready();}
 target.append(current);
}
function installMetricEffects(holder,status){
 const view=metricVisualState(status),cards=holder.querySelectorAll('.metric');
 const cpu=cards[2];if(cpu.dataset.visualState)cpu.classList.remove('cpu-'+cpu.dataset.visualState);cpu.dataset.visualState=view.cpuBand;cpu.classList.add('cpu-'+view.cpuBand);
 stateGraphic(cpu.querySelector('.metric-label>.ui-icon'),FINAL_DESIGN_ASSETS.furnace[view.cpuBand]);cpu.querySelector('.metric-value').replaceChildren(view.cpu===null?'—':decimal(view.cpu),node('small',{text:'%'}));
 if(view.cpu===null){cpu.querySelector('meter')?.remove();cpu.querySelector('.metric-state')?.remove();}else{const description=cpu.querySelector('.metric-state')||node('div',{class:'metric-state'});description.textContent=t('metricCpu_'+view.cpuBand);if(!description.parentNode)cpu.append(description);}
 const storage=cards[5];if(storage.dataset.visualState)storage.classList.remove('storage-'+storage.dataset.visualState);storage.dataset.visualState=view.storageBand;storage.classList.add('storage-'+view.storageBand);
 stateGraphic(storage.querySelector('.metric-label>.ui-icon'),FINAL_DESIGN_ASSETS.chest[view.storageBand]);
 storage.querySelector('.metric-label').lastElementChild.textContent=t('disk');
 storage.querySelector('.metric-value').firstChild.nodeValue=view.used===null?'—':bytes(status.disk.total-status.disk.free);
 const meter=storage.querySelector('meter');if(meter&&view.used!==null){meter.value=view.used;meter.setAttribute('aria-label',t('metricStorageUsed'));}else meter?.remove();
 const storageNote=storage.querySelector('.metric-footnote')||node('div',{class:'metric-footnote'});if(!storageNote.parentNode)storage.append(storageNote);storageNote.textContent=view.used===null?'':bytes(status.disk.total)+' '+t('metricTotal')+' · '+view.used.toLocaleString(state.language,{maximumFractionDigits:1})+'% '+t('metricUsed');
 const tps=cards[4];if(tps.dataset.visualState)tps.classList.remove('quality-'+tps.dataset.visualState);tps.dataset.visualState=view.qualityBand;tps.classList.add('quality-'+view.qualityBand);
 stateGraphic(tps.querySelector('.metric-label>.ui-icon'),FINAL_DESIGN_ASSETS.redstone[view.qualityArtworkState]);
 if(view.quality!==null){tps.querySelector('meter').value=view.quality*100;const description=tps.querySelector('.metric-state')||node('div',{class:'metric-state'});description.textContent=t('metricQuality_'+view.qualityBand);if(!description.parentNode)tps.append(description);}else{tps.querySelector('meter')?.remove();tps.querySelector('.metric-state')?.remove();}
 const oldFigures=cards[1].querySelector('.metric-label>.ui-icon'),figures=oldFigures.classList.contains('players-figures')?oldFigures:node('span');if(figures!==oldFigures)oldFigures.replaceWith(figures);figures.className='ui-icon status-visual players-figures';figures.dataset.figureCount=String(view.visiblePlayers);while(figures.children.length>view.visiblePlayers)figures.lastElementChild.remove();
 for(let i=0;i<view.visiblePlayers;i++){const src=originalAsset(FINAL_DESIGN_ASSETS.players[i]),previous=figures.children[i];if(src&&previous?.getAttribute('src')!==src){const next=node('img',{class:'player-sprite is-online',src,alt:'',width:100,height:100,decoding:'async'});if(previous)previous.replaceWith(next);else figures.append(next);}}
 if(view.visiblePlayers&&!figures.children.length)figures.append(node('span',{class:'reference-art-missing',text:t('originalArtworkMissing')}));
 cards[1].querySelector('.metric-value').replaceChildren(String(view.players??'—'));
 if(view.players>3)cards[1].querySelector('.metric-value').append(node('span',{class:'player-extra','aria-hidden':'true',text:'+'+(view.players-3)}));
 cards[1].classList.toggle('players-empty',view.players===0);const uptime=cards[6],oldClock=uptime.querySelector('.metric-label>.ui-icon'),clock=oldClock.classList.contains('reference-clock')?oldClock:node('span'),art=FINAL_DESIGN_ASSETS.clock;if(clock!==oldClock)oldClock.replaceWith(clock);
 if(view.elapsed!==null&&clock.querySelector('.clock-art')){clock.classList.remove('visual-unknown');clock.dataset.started=String(view.started);updateUptimeGraphic(clock);return;}
 if(view.elapsed===null&&clock.classList.contains('visual-unknown')&&clock.querySelector('img')?.getAttribute('src')===originalAsset(art.face)){uptime.querySelector('.metric-value').replaceChildren('—');return;}
 clock.className='ui-icon status-visual reference-clock';clock.replaceChildren();
 if(view.elapsed===null)uptime.querySelector('.metric-value').replaceChildren('—');if(view.elapsed!==null&&originalAsset(art.face)&&originalAsset(art.hour)&&originalAsset(art.minute)){
  clock.classList.add('uptime-graphic');clock.dataset.started=String(view.started);clock.dataset.pivot='256,300';
  const previousClock=document.querySelector('.uptime-graphic .clock-art');clock.append(previousClock||svgNode('svg',{class:'clock-art',viewBox:'0 0 512 512','aria-hidden':'true'},svgNode('image',{href:originalAsset(art.face),width:512,height:512}),svgNode('g',{class:'clock-hour'},svgNode('image',{href:originalAsset(art.hour),width:512,height:512})),svgNode('g',{class:'clock-minute'},svgNode('image',{href:originalAsset(art.minute),width:512,height:512})),svgNode('image',{href:originalAsset(art.pivot),width:512,height:512})));updateUptimeGraphic(clock);
 }else{clock.classList.add('visual-unknown');clock.append(node('img',{src:originalAsset(art.face),alt:'',width:512,height:512,decoding:'async'}));}
}
document.addEventListener('visibilitychange',()=>{document.documentElement.classList.toggle('page-hidden',document.hidden);for(const entry of metricAnimations){if(document.hidden)entry.animation.pause();else{entry.animation.currentTime=Math.max(0,(Date.now()-entry.started)%60000);entry.animation.play();}}});
setInterval(()=>{if(!document.hidden){const clock=document.querySelector('.uptime-graphic[data-started]');if(clock)updateUptimeGraphic(clock);}},1000);

function confirmAction(message,action){modal('confirmOperation',node('div',{},paragraph(message),node('div',{class:'form-actions'},button('cancel',closeModal),button('yes',async()=>{closeModal();await action();},'primary'))));}
let pageRenderGeneration=0,eventsRequestGeneration=0;
let pageLiveRefresh=null,pageLiveBusy=false;
async function renderPage(){updateEventAccess();pageLiveRefresh=null;const generation=++pageRenderGeneration,page=state.page;stopMetricEffects();document.querySelectorAll('[data-page]').forEach(x=>{x.classList.toggle('active',x.dataset.page===state.page);if(x.dataset.page===state.page)x.setAttribute('aria-current','page');else x.removeAttribute('aria-current');});try{if(page==='overview')await overviewPage(generation);if(page==='mods')await modsPage(generation);if(page==='backups')await backupsPage();if(page==='events')await eventsPage(state.eventView?.category||'',generation);if(generation===pageRenderGeneration){decoratePanelHeaders();if(page!=='mods'&&state.user.admin)attempt(refreshChangeBasket);if(page!=='overview')attempt(refreshGlobalJobs);}}catch(error){if(error.code==='authentication_required'){loginScreen();return;}throw error;}}
function overviewMetrics(overview){const status=overview.status;const holder=node('div',{class:'metrics'},metric('server',t(status.container_status||'unknown'),'',overview.server.version+' · '+loaderLabel(status.runtime||overview.server)),metric('playersOnline',status.players_online),metric('cpu',status.cpu_percent===null||status.cpu_percent===undefined?'—':decimal(status.cpu_percent),'%'),metric('memory',bytes(status.memory_used),'',bytes(status.memory_limit)),metric('tps',status.tps===null||status.tps===undefined?'—':decimal(status.tps),'TPS',status.mspt===null||status.mspt===undefined?'—':decimal(status.mspt)+' ms/tick'),metric('disk',status.disk?bytes(status.disk.free):'—','',status.disk?bytes(status.disk.total):''),metric('uptime',status.container_status==='running'&&status.started_at?duration((Date.now()-Date.parse(status.started_at))/1000):'—','',status.container_status==='running'&&status.started_at?t('onlineSince')+': '+date(status.started_at):''));
const gauges=[['cpu',2,metricVisualState(status).cpu],['memory',3,status.memory_limit?status.memory_used/status.memory_limit*100:null],['tps',4,typeof status.tps==='number'?status.tps/20*100:null],['disk',5,status.disk?.total?status.disk.free/status.disk.total*100:null]];for(const [label,index,value] of gauges){if(typeof value==='number'&&Number.isFinite(value)){const gauge=node('meter',{class:'metric-meter',min:0,max:100,value:Math.max(0,Math.min(100,value)),'aria-label':t(label)});holder.querySelectorAll('.metric')[index].append(gauge);}}
installMetricEffects(holder,status);return holder;}
function updateOverviewMetrics(holder,overview){
 const status=overview.status,cards=holder.querySelectorAll('.metric'),view=metricVisualState(status);
 const server=cards[0],serverLabel=t(status.container_status||'unknown'),serverState=serverLabel===t('running')?'online':serverLabel===t('unknown')?'unknown':'offline';
 for(const key of ['online','unknown','offline'])server.classList.toggle('metric-'+key,key===serverState);
 server.querySelector('.metric-value').replaceChildren(node('span',{class:'server-state-dot'}),serverLabel);
 function note(card,text){const target=card.querySelector('.metric-footnote')||node('div',{class:'metric-footnote'});target.textContent=text;if(!target.parentNode)card.append(target);}
 note(server,overview.server.version+' · '+loaderLabel(status.runtime||overview.server));
 cards[3].querySelector('.metric-value').replaceChildren(bytes(status.memory_used));note(cards[3],bytes(status.memory_limit));
 cards[4].querySelector('.metric-value').replaceChildren(status.tps==null?'—':decimal(status.tps),node('small',{text:'TPS'}));note(cards[4],status.mspt==null?'—':decimal(status.mspt)+' ms/tick');
 const started=status.container_status==='running'&&status.started_at;note(cards[6],started?t('onlineSince')+': '+date(status.started_at):'');
 for(const [label,index,value] of [['cpu',2,view.cpu],['memory',3,status.memory_limit?status.memory_used/status.memory_limit*100:null],['tps',4,view.quality===null?null:view.quality*100],['disk',5,view.used]]){
  const card=cards[index],old=card.querySelector('meter');if(typeof value!=='number'||!Number.isFinite(value)){old?.remove();continue;}
  const gauge=old||node('meter',{class:'metric-meter',min:0,max:100,'aria-label':t(label)});gauge.value=Math.max(0,Math.min(100,value));if(!gauge.parentNode)card.append(gauge);
 }
 installMetricEffects(holder,status);
}
let overviewLiveRefresh=null,overviewLiveBusy=false;
async function overviewPage(generation=pageRenderGeneration){const remainder=Promise.all([api('/players'),api('/jobs?summary=true')]);remainder.catch(()=>{});const overview=await api('/overview');if(generation!==pageRenderGeneration)return;const status=overview.status;const actions=[button('refresh',renderPage)];if(state.user.admin){actions.push(button('start',()=>queue('server',{operation:'start'})),button('restart',()=>maintenanceChoice('server',{operation:'restart'})),button('stop',()=>maintenanceChoice('server',{operation:'stop'}),'danger'));}const holder=node('div',{},heading('overview','serverIntro',actions),state.user.admin?node('nav',{class:'form-actions settings-shortcuts','aria-label':t('quickSettings')},button('serverProperties',()=>settings('serverProperties')),button('worldManagement',()=>settings('worldManagement')),button('localRuntimeFiles',()=>settings('runtimeSettings','localRuntimeFiles'))):null,overviewMetrics(overview));
$('page-content').replaceChildren(holder);const loading=node('div',{class:'overview-loading',role:'status',text:t('loading')});holder.append(loading);let [players,jobs]=await remainder;if(generation!==pageRenderGeneration)return;if(Object.prototype.hasOwnProperty.call(players,'online_count')){overview.status.players_online=players.online_count;updateOverviewMetrics(holder.querySelector('.metrics'),overview);}updateGlobalJobs(jobs);loading.remove();
const playerCard=node('section',{class:'card players-card'},node('div',{class:'card-head'},node('div',{},node('h3',{text:t('players')}),node('div',{class:'hint',text:t('visitorHint')}))));const search=input('search','',{placeholder:t('playerSearch')});const role=select([['','allRoles'],['visitor','visitor'],['player','player'],['moderator','moderator'],['administrator','administrator']],'');const list=node('div');function filter(){const records=(players.players||[]).filter(x=>(!role.value||x.role===role.value)&&((x.name||'')+' '+x.uuid).toLowerCase().includes(search.value.toLowerCase()));list.replaceChildren(table(['name','uuid','presence','role','lastSeen','playTime','actions'],records.map(x=>[node('strong',{text:x.name}),node('code',{class:'player-uuid',text:x.uuid}),pill(x.online===true?'online':x.online===false?'offline':'presenceUnknown',x.online===true?'good':x.online===false?'':'warn'),pill(x.role||'visitor'),date(x.last_seen),duration((x.play_seconds||0)+(x.online_since?Date.now()/1000-x.online_since:0)),state.user.admin?button('actions',()=>playerActions(x)):node('span',{text:'—'})]),'noPlayers'));}search.addEventListener('input',filter);role.addEventListener('change',filter);playerCard.append(node('div',{class:'search-bar'},search,role),list);filter();if(state.user.admin)playerCard.append(button('playerAdmission',async()=>modal('playerAdmission',await playerAdmissionPanel())));holder.append(playerCard);
const output=node('pre',{class:'console-output',text:t('consoleHint')});const command=input('text','',{placeholder:t('command'),maxLength:2000,required:true});const consoleForm=node('form',{class:'console-form'},command,node('button',{type:'submit',text:t('send')}));consoleForm.addEventListener('submit',event=>{event.preventDefault();attempt(async()=>{const result=await api('/console',{command:command.value});output.textContent=result.output;command.value='';});});const chatMessage=input('text','',{required:true,maxLength:500});const chatForm=form([field('chat',chatMessage)],'send',async()=>{await api('/chat',{message:chatMessage.value});chatMessage.value='';toast(t('chat_sent'));});const consoleCard=node('section',{class:'card console-card'},node('div',{class:'card-head'},node('h3',{text:t('console')})),node('div',{class:'card-body'},output,state.user.admin?consoleForm:null,state.user.admin?chatForm:null));let jobCard=maintenancePanel(jobs);const protection=state.user.admin?backupProtectionPanel():null;if(protection){holder.append(protection.element);await protection.refresh();}holder.append(node('div',{class:'two-columns'},consoleCard,jobCard));$('page-content').replaceChildren(holder);
overviewLiveRefresh=async()=>{if(overviewLiveBusy||state.page!=='overview'||!holder.isConnected)return;overviewLiveBusy=true;try{
 const [liveOverview,livePlayers,liveJobs]=await Promise.all([api('/overview'),api('/players'),api('/jobs?summary=true')]);if(generation!==pageRenderGeneration||!holder.isConnected)return;
 if(Object.prototype.hasOwnProperty.call(livePlayers,'online_count'))liveOverview.status.players_online=livePlayers.online_count;updateGlobalJobs(liveJobs);updateOverviewMetrics(holder.querySelector('.metrics'),liveOverview);players=livePlayers;filter();const replacement=maintenancePanel(liveJobs);jobCard.replaceWith(replacement);jobCard=replacement;if(protection)await protection.refresh();decoratePanelHeaders();
 }finally{overviewLiveBusy=false;}};
}
function playerActions(player){
 const holder=node('div',{class:'stack'},node('h3',{text:player.name}),node('small',{text:player.uuid}));
 const group=select([['visitor','visitor'],['player','player'],['moderator','moderator'],['administrator','administrator']],player.role||'visitor');
 async function change(action,value={}){await api('/players/action',{uuid:player.uuid,action,...value});toast(t('recorded'));closeModal();await renderPage();}
 holder.append(form([field('role',group)],'save',()=>change('role',{role:group.value})));
 const whitelist=input('checkbox');whitelist.checked=!!player.whitelisted;
 holder.append(form([node('label',{class:'checkbox-field'},whitelist,t('whitelist'))],'save',()=>change('whitelist',{enabled:whitelist.checked})));
 const operator=input('checkbox');operator.checked=!!player.op;operator.disabled=player.role!=='administrator';
 holder.append(form([node('label',{class:'checkbox-field'},operator,t('op')),paragraph('mcOpHint','hint')],'save',()=>change('op',{enabled:operator.checked})));
 const reason=input('text','',{maxLength:150,placeholder:t('reason')});
 holder.append(field('reason',reason),node('div',{class:'form-actions'},
  button('kick',()=>change('kick',{reason:reason.value}),'danger'),
  button(player.banned?'unban':'ban',async()=>{if(!reason.value.trim()){reason.setCustomValidity(t('reasonRequired'));reason.reportValidity();return;}await change(player.banned?'unban':'ban',{reason:reason.value});},'danger')));
 reason.addEventListener('input',()=>reason.setCustomValidity(''));modal('actions',holder);
}
function serverJobTitle(operation){return ['start','stop','restart'].includes(operation)?t('serverAction_'+operation):t('maintenanceAction');}
function maintenanceChoice(kind,payload={},description=null){
 const options=select([['immediate','restartImmediately'],['idle_now','restartIdleNow'],['idle_5min','restartIdleFive'],['scheduled','specificTime'],['manual','stageOnly']],'idle_now');
 const disconnect=input('checkbox');const warning=node('label',{class:'warning-box checkbox-field'},disconnect,t('disconnectPlayersWarning'));warning.hidden=true;
 const chosen=input('datetime-local','',{required:true}),calendar=field('berlinDateTime',chosen),preview=node('p',{class:'info-box',role:'status'});calendar.hidden=true;
 function update(){warning.hidden=options.value!=='immediate';disconnect.required=!warning.hidden;calendar.hidden=options.value!=='scheduled';chosen.required=!calendar.hidden;preview.textContent=options.value==='scheduled'?(chosen.value?chosen.value.replace('T',' · ')+' · Europe/Berlin':t('chooseDateTime')):t(options.value==='immediate'?'restartImmediately':options.value==='manual'?'stageOnly':options.value==='idle_5min'?'restartIdleFive':'restartIdleNow');}options.addEventListener('change',update);chosen.addEventListener('input',update);update();
 const review=node('section',{class:'maintenance-review'},node('h3',{text:t('changeReview')}),paragraph('loading'));
 api('/overview').then(value=>{if(!review.isConnected)return;const current=value.server,lines=[];if(description)lines.push(description);if(payload.include_pending_mods)lines.push(t('includeCollectedMods'));if(kind==='server_settings'){for(const [key,next] of Object.entries(payload.changes?.properties||{}))lines.push(key+': '+displayText(current.properties?.[key]??'—')+' → '+displayText(next));if(payload.changes?.memory_mb!==undefined)lines.push(t('memoryBudget')+': '+current.memory_mb+' → '+payload.changes.memory_mb);if(payload.changes?.container_memory_mb!==undefined)lines.push(t('containerMemoryBudget')+': '+(current.container_memory_mb??8192)/1024+' → '+payload.changes.container_memory_mb/1024+' GiB · Java '+(payload.changes.container_memory_mb/1024-2)+' GiB');}else if(kind==='server')lines.push(serverJobTitle(payload.operation));else if(payload.name)lines.push(t('worldName')+': '+payload.name);else lines.push(jobTitle({kind,purpose:'version'}));review.replaceChildren(node('h3',{text:t('changeReview')}),node('ul',{},lines.map(text=>node('li',{text}))),node('p',{text:t('currentlyActive')+': Minecraft '+current.version+' · '+loaderLabel(current)}),node('p',{text:t('playersOnline')+': '+displayText(value.status.players_online??t('presenceUnknown'))}),paragraph(['mod_check','source_check','source_stage','restore_test'].includes(kind)?'reviewNoRestart':'reviewRestart'));}).catch(()=>review.replaceChildren(paragraph('reviewUnavailable')));
 const needsCapacity=['backup','apply_mods','server_settings','version_test','version_apply','restore','restore_test','world_change','world_delete','world_export','curseforge_install'].includes(kind);
 const capacity=node('section',{class:'storage-preflight',role:'status'},paragraph('storageChecking'));capacity.hidden=!needsCapacity;let forecast=null,capacitySubmit=null;
 function capacityEnabled(){if(capacitySubmit)capacitySubmit.disabled=needsCapacity&&options.value!=='manual'&&(!forecast||!forecast.sufficient);}options.addEventListener('change',capacityEnabled);
 if(needsCapacity)api('/storage/preflight',{kind,...(payload.id?{id:payload.id}:{})}).then(value=>{forecast=value;capacity.replaceChildren(node('h3',{text:t('storagePreflight')}),paragraph(value.sufficient?'storageEnough':'insufficient_operation_space',value.sufficient?'hint':'warning-box'),...value.volumes.map(volume=>node('p',{class:'info-box',text:volume.roles.map(role=>t('storageRole_'+role)).join(' + ')+': '+t('storageFree')+' '+bytes(volume.free_bytes)+' · '+t('storageRequired')+' '+bytes(volume.required_bytes)+' · '+t('storageReserve')+' '+bytes(volume.reserve_bytes)})),paragraph('storageEstimateHint','hint'));capacityEnabled();}).catch(()=>{capacity.replaceChildren(paragraph('storage_preflight_unavailable','warning-box'));capacityEnabled();});
 const appliesAfterCheck=['apply_mods','server_settings'].includes(kind),applyHint=paragraph('autoApplyAfterCheck','info-box');applyHint.hidden=!appliesAfterCheck;
 const operationHint=kind==='backup'?'backupOperationHint':kind==='server'?'serverOperationHint':['world_delete','world_export'].includes(kind)?'worldFileOperationHint':'maintenanceChoiceHint';
 options.addEventListener('change',()=>{if(appliesAfterCheck)applyHint.textContent=t(options.value==='manual'?'stagedApplyLater':'autoApplyAfterCheck');});
 const choiceForm=form([paragraph(operationHint),applyHint,review,capacity,field('restartChoice',options),calendar,preview,warning],appliesAfterCheck?'checkAndApplyChanges':'confirmSchedule',async()=>{
  const manual=options.value==='manual';if(needsCapacity&&!manual&&(!forecast||!forecast.sufficient)){toast(t(forecast?'insufficient_operation_space':'storage_preflight_unavailable'));return;}await api('/jobs',{kind,payload:Object.fromEntries(Object.entries(payload).filter(([key])=>!['_collected_settings','_settings_form_review'].includes(key))),mode:options.value,approved:!manual,disconnect_confirmed:options.value==='immediate'&&disconnect.checked,...(options.value==='scheduled'?{schedule_local:chosen.value}:{})});if(payload._collected_settings&&pendingSettingsChanges?.basis===payload.basis){pendingSettingsChanges=null;updateChangeBasket();}if(settingsReturnView){const category={server_settings:'serverProperties',world_change:'worldManagement',version_test:'runtimeSettings',version_apply:'runtimeSettings'}[kind];if(category&&!(kind==='server_settings'&&payload._collected_settings&&!payload._settings_form_review))for(const form of settingsDraftState.root.querySelectorAll('[data-settings-category='+category+'] form'))markSettingsFormSaved(form,true);if(settingsDraftDirty()){restoreSettingsReturn();toast(t('jobQueued'));await renderPage();await refreshGlobalJobs();return;}}closeModal(true);toast(t('jobQueued'));await renderPage();await openMaintenance();
 });capacitySubmit=choiceForm.querySelector('[type=submit]');if(appliesAfterCheck)options.addEventListener('change',()=>{capacitySubmit.textContent=t(options.value==='manual'?'stageChanges':'checkAndApplyChanges');});capacityEnabled();modal('maintenance',choiceForm,{preserveSettings:true});
}
async function modsPage(generation=pageRenderGeneration){
 const result=await api('/mods');updateChangeBasket(result);const fileInput=input('file','',{multiple:true,accept:'.jar',class:'file-input'});
 async function upload(files){const body=new FormData();for(const file of files)body.append('files',file);await api('/mods/upload',body);await renderPage();toast(t('modChangesCollected'));}
 fileInput.addEventListener('change',()=>attempt(()=>upload(fileInput.files)));
 const drop=node('div',{class:'dropzone'},icon('backups'),node('div',{},node('h3',{text:t('uploadTitle')}),paragraph('uploadIntro')),button('chooseFiles',()=>fileInput.click()),fileInput);
 drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('drag');});drop.addEventListener('dragleave',()=>drop.classList.remove('drag'));
 drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('drag');attempt(()=>upload(event.dataTransfer.files));});
 const search=input('search',state.modSearch,{placeholder:t('modSearch')});const statusFilter=select([['all','allMods'],['active','enabled'],['inactive','disabled'],['staged','staged'],['updates','available'],['errors','failed']],state.modFilter);const listing=node('div');
 function filter(){
  const rows=result.mods.filter(x=>state.modFilter==='all'||state.modFilter==='active'&&x.installed_enabled||state.modFilter==='inactive'&&!x.installed_enabled||state.modFilter==='staged'&&x.state==='staged'||state.modFilter==='updates'&&['available','update_prepared'].includes(x.available.status)||state.modFilter==='errors'&&x.error).filter(x=>(x.filename+' '+x.metadata.mods.map(m=>m.name+' '+m.id).join(' ')).toLowerCase().includes(search.value.toLowerCase())).map(x=>{
   const enabled=input('checkbox');enabled.checked=!!x.enabled;enabled.disabled=!state.user.admin||x.protected||x.metadata.client_installer||x.remove_pending!=null;
   enabled.addEventListener('change',()=>attempt(async()=>{const desired=enabled.checked;enabled.disabled=true;try{await api('/mods/'+x.id+'/desired',{enabled:desired});x.enabled=desired;updateChangeBasket(result);filter();toast(t('modChangesCollected'));}catch(error){enabled.checked=!!x.enabled;throw error;}finally{enabled.disabled=false;}}));
   const details=node('details',{},node('summary',{text:t('dependencies')}),node('ul',{},(x.metadata.dependencies||[]).map(d=>node('li',{text:d.id+' '+(Array.isArray(d.range)?d.range.join(' / '):d.range)}))));
   if(x.metadata.embedded?.length)details.append(node('p',{text:t('embeddedModules')+': '+x.metadata.embedded.length}),node('ul',{},x.metadata.embedded.flatMap(m=>m.mods).map(m=>node('li',{text:m.name+' '+m.version}))));
   return [node('div',{},node('strong',{text:x.metadata.client_installer?t('clientInstallerTitle'):x.metadata.mods.map(m=>m.name).join(', ')}),node('small',{text:x.filename}),details),x.metadata.mods.map(m=>m.version).join(', '),
    node('div',{},pill(x.metadata.client_installer?'clientInstallerNotApplicable':x.protected?'system_managed':x.available.status==='not_checked'?'modUpdateNotChecked':x.available.status,x.available.status==='available'&&!x.protected?'warn':''),node('small',{text:x.available.version||'—'}),x.pending_update?node('small',{text:t('updatePendingInstall')+' · '+x.pending_update.filename}):null,x.available.status==='available'&&state.user.admin&&!x.protected&&x.remove_pending==null?button('stageModUpdate',async()=>{await api('/mods/'+x.id+'/update',{});await renderPage();toast(t('modChangesCollected'));}):null),node('div',{},node('span',{text:t(x.locally_patched?'localPatchOrigin':x.source)}),x.locally_patched?node('small',{text:t('localPatchUpdateHint')}):null,x.upstream_url?node('a',{href:x.upstream_url,target:'_blank',rel:'noopener noreferrer',text:t('originalProject')}):null),node('div',{},pill(x.remove_pending!=null?'modRemovalPending':x.metadata.client_installer?'clientInstallerNotServer':x.state,x.metadata.client_installer?'warn':x.state==='failed'?'bad':x.state==='staged'?'warn':''),x.error?node('small',{text:errorText(x.error)}):null),
    node('div',{},node('label',{class:'checkbox-field'},enabled,t(x.enabled?'enabled':'disabled')),node('small',{text:t('currentlyOnServer')+': '+t(x.installed_enabled?'enabled':'disabled')}),x.metadata.client_installer?(x.error?null:node('small',{text:t('client_installer_not_server_mod')})):x.protected?node('small',{text:t('protectedMod')}):x.state!=='installed'||!!x.enabled!==!!x.installed_enabled?node('small',{text:t('pendingUntilApply')}):null,state.user.admin&&!x.protected&&x.pending_update?button('cancelPendingModUpdate',()=>confirmAction('cancelPendingModUpdateHint',async()=>{await api('/mods/'+x.id+'/update/cancel',{});closeModal();await renderPage();})):null,state.user.admin&&!x.protected&&x.state==='installed'&&!x.pending_update&&x.remove_pending==null&&hasVersionProvider(x)?button('chooseModVersion',()=>chooseModVersion(x)):null,state.user.admin&&!x.protected?button(x.remove_pending!=null?'cancelModRemoval':'uninstallMod',()=>requestModRemoval(x),x.remove_pending!=null?'':'danger'):null)];
  });listing.replaceChildren(table(['name','installedVersion','modUpdateCheck','source','status','enabled'],rows,'noMods'));
 }
 search.addEventListener('input',()=>{state.modSearch=search.value;filter();});statusFilter.addEventListener('change',()=>{state.modFilter=statusFilter.value;filter();});
 const actions=[button('checkUpdates',()=>queue('mod_check')),node('a',{href:'/api/mods/export',class:'text-button',text:t('exportMods')})];
 if(state.user.admin)actions.push(button('installMods',openCollectedChanges,'primary'));
 const holder=node('div',{},heading('mods','modsIntro',actions),state.user.admin?drop:null,state.user.admin?curseForgeSearchPanel(result.mods):null,node('section',{class:'card mod-filters'},node('div',{class:'search-bar'},search,statusFilter)),node('section',{class:'card mods-list'},node('div',{class:'card-body mod-state-help'},paragraph('modUpdateCheckHint','hint'),paragraph('modActivationHint','hint')),listing));
 if(state.user.admin)holder.append(await clientPackPanel());
 holder.append(await sourcePanel());
 if(result.dependencies.issues?.length)holder.append(node('div',{class:'info-box'},paragraph('metadataBlocked'),node('ul',{},result.dependencies.issues.map(x=>node('li',{text:t(x.issue)+(x.dependency?' · '+x.dependency:'')})))));
 filter();if(generation!==pageRenderGeneration)return;$('page-content').replaceChildren(holder);
 pageLiveRefresh=async()=>{const next=await api('/mods');if(generation!==pageRenderGeneration||!holder.isConnected||listing.contains(document.activeElement))return;Object.assign(result,next);updateChangeBasket(result);filter();const source=holder.querySelector('.source-records')?.parentElement;if(source?.refreshFacts)await source.refreshFacts();await refreshGlobalJobs();};
}
async function requestModRemoval(mod){
 if(mod.remove_pending!=null){await api('/mods/'+mod.id+'/removal',{remove:false});await renderPage();return;}
 const body=node('div',{class:'stack'},node('strong',{text:mod.metadata.mods.map(x=>x.name).join(', ')}),paragraph('uninstallModHint'),node('div',{class:'form-actions'},button('uninstallMod',async()=>{await api('/mods/'+mod.id+'/removal',{remove:true});closeModal();await renderPage();toast(t('modChangesCollected'));},'danger'),button('cancel',closeModal)));
 modal('uninstallMod',body);
}
async function sourcePanel(){
 const [data,jobs]=await Promise.all([api('/mods/sources'),api('/jobs?summary=true')]);
 const holder=node('section',{class:'card mod-test-results'},node('div',{class:'card-body'},node('h3',{text:t('modSources')}),paragraph('modSourcesIntro','hint')));
 if(state.user.admin)holder.append(node('div',{class:'card-body form-actions'},button('editSources',()=>editSources(data.sources)),button('importPackZip',()=>importPackZip(data.sources))));
 const rows=data.sources.map(source=>{
  const job=jobs.find(j=>['source_check','source_stage'].includes(j.kind)&&['queued','running'].includes(j.state)&&JSON.parse(j.payload).id===source.id);
  const report=source.report||{},installation=source.installation||{};const check=button('checkSource',()=>queue('source_check',{id:source.id}));check.disabled=!!job;
  const stage=button('stageSource',()=>queue('source_stage',{id:source.id}));stage.disabled=!!job||['blocked','unavailable'].includes(report.state);stage.title=stage.disabled&&report.reason?errorText(report.reason):'';
  return [node('div',{},node('strong',{text:report.name||source.slug}),node('small',{},node('a',{href:source.url,target:'_blank',rel:'noopener noreferrer',text:source.url}))),
   node('div',{},pill(job?'state_'+job.state:installation.pending?.length?'sourceChangesPending':installation.active?.length?'sourceInstalledActive':installation.inactive?.length?'sourceInstalledInactive':report.state||'not_checked',job||installation.pending?.length?'warn':installation.active?.length?'good':''),report.state==='metadata_checked'?node('small',{text:t('sourceMetadataOnly')}):null,installation.active?.length?node('small',{text:installation.active.join(', ')}):null,installation.pending?.length?node('small',{text:t('sourceApplyHint')}):null,installation.locally_modified?node('small',{text:t('localPatchOrigin')}):null,report.reason?node('small',{text:errorText(report.reason)}):null,report.checked?node('small',{text:date(report.checked)}):null,
    source.staged?node('small',{text:t('filesStaged')+': '+source.staged.files+' · '+date(source.staged.at)}):null),
   state.user.admin?node('div',{class:'form-actions'},check,stage):null];
 });const facts=node('div',{class:'source-records'},table(['source','status','actions'],rows,'noModSources'));holder.append(facts);holder.refreshFacts=async()=>{if(!holder.isConnected)return;const fresh=await sourcePanel();if(holder.isConnected)facts.replaceChildren(...fresh.querySelector('.source-records').childNodes);};
 for(const plan of data.pending_packs){
  const enabled=input('checkbox');enabled.checked=!!plan.apply_properties;enabled.disabled=!state.user.admin;
  enabled.addEventListener('change',()=>attempt(async()=>{await api('/mods/packs/'+plan.id+'/properties',{enabled:enabled.checked});toast(t('saved'));}));
  holder.append(node('div',{class:'card-body'},node('h4',{text:t(plan.name)}),node('p',{text:t('packConfigurationFiles')+': '+plan.files.length}),paragraph('packPendingHint','hint'),
   Object.keys(plan.properties).length?node('details',{},node('summary',{text:t('packServerProperties')}),table(['property','value'],Object.entries(plan.properties).map(([key,value])=>[key,value])),node('label',{class:'checkbox-field'},enabled,t('applyPackProperties'))):null));
 }
 return holder;
}
function editSources(sources){
 const list=node('div',{class:'stack'});const entries=[];
 function add(value={url:'',enabled:true,allow_prerelease:false}){
  const url=input('url',value.url,{required:true,maxLength:400});const enabled=input('checkbox');enabled.checked=value.enabled;
  const beta=input('checkbox');beta.checked=!!value.allow_prerelease;const entry={url,enabled,beta};entries.push(entry);
  const row=node('div',{class:'setting-section'},field('sourceUrl',url),node('label',{class:'checkbox-field'},enabled,t('watchSource')),node('label',{class:'checkbox-field'},beta,t('allowBetaFiles')),
   button('removeSource',()=>{entries.splice(entries.indexOf(entry),1);row.remove();}));list.append(row);
 }
 sources.forEach(add);
 modal('editSources',form([paragraph('sourceUrlHint','hint'),list,button('addSource',()=>add())],'save',async()=>{
  await api('/mods/sources',{sources:entries.map(x=>({url:x.url.value,enabled:x.enabled.checked,allow_prerelease:x.beta.checked}))});closeModal();await renderPage();
 }));
}
function importPackZip(sources){
 const file=input('file','',{accept:'.zip',required:true});const origin=select([['','ownPackZip'],...sources.filter(x=>x.kind==='pack'&&x.provider==='curseforge').map(x=>[x.id,x.slug])],'');
 const beta=input('checkbox');modal('importPackZip',form([paragraph('packZipHint','hint'),field('packFile',file),field('packOrigin',origin),node('label',{class:'checkbox-field'},beta,t('allowBetaFiles'))],'stageSource',async()=>{
  if(file.files.length!==1)return;
  const query=new URLSearchParams({allow_prerelease:String(beta.checked)});if(origin.value)query.set('source_id',origin.value);
  await api('/packs/upload?'+query,file.files[0]);closeModal();await renderPage();toast(t('modChangesCollected'));
 }));
}
function restoreBackup(backup){
 const confirmation=input('text','',{required:true,autocomplete:'off'});const expected='restore '+backup.id;
 modal('restore',form([paragraph('restoreWarning'),node('p',{text:date(backup.created)+' · '+bytes(backup.size)}),node('code',{text:expected}),field('restoreConfirmation',confirmation)],'restore',async()=>{
  if(confirmation.value!==expected){confirmation.setCustomValidity(t('restore_confirmation_required'));confirmation.reportValidity();return;}
  maintenanceChoice('restore',{id:backup.id,confirmation:confirmation.value});
 }));confirmation.addEventListener('input',()=>confirmation.setCustomValidity(''));
}
async function playerAdmissionPanel(){
 const panel=node('section',{class:'stack player-admission'},node('h4',{text:t('playerAdmission')}),paragraph('playerAdmissionHint','hint'));
 try{
  const view=await api('/player-admission');
  panel.append(node('p',{text:t(view.open_to_new_players?'playerAdmissionOpen':'playerAdmissionNamesOnly')}));
  if(view.open_to_new_players!==view.configured_open)panel.append(paragraph('playerAdmissionPending','hint'));
  if(!view.can_open)panel.append(paragraph('visitor_admission_requires_verified_guard','info-box'));
  const change=button(view.configured_open?'playerAdmissionClose':'playerAdmissionAllow',()=>maintenanceChoice('server_settings',{changes:{properties:{'white-list':view.configured_open?'true':'false'}},basis:view.basis},t(view.configured_open?'playerAdmissionCloseHint':'playerAdmissionConfirm')));
  change.disabled=!view.configured_open&&!view.can_open;
  panel.append(change,paragraph('playerAdmissionInternet','hint'));
 }catch(error){if(error.code==='authentication_required')throw error;panel.append(errorParagraph(error.code));}
 return panel;
}
function backupProtectionPanel(){
 const last=node('p'),age=node('p'),due=node('p'),waiting=node('p'),warning=node('p',{class:'notice warning',hidden:true,text:t('backupOverdue')});
 const element=node('section',{class:'card',role:'status','aria-live':'polite'},node('h3',{text:t('backupProtection')}),last,age,due,waiting,warning,paragraph('backupTimingHint','hint'));
 async function refresh(){
  const view=await api('/backups/schedule');
  last.textContent=view.last_success==null?t('backupNever'):t('backupLastSuccess')+': '+date(view.last_success);
  age.textContent=view.age_seconds==null?'':t('backupAge')+': '+duration(view.age_seconds);
  due.textContent=t('backupNextDue')+': '+(view.enabled?date(view.due_at):t('disabled'));
  waiting.textContent=view.wait_reason?t('backupWait_'+view.wait_reason)+(view.wait_reason==='scheduled'?': '+date(view.pending.scheduled_at)+' · Europe/Berlin':''):'';
  warning.hidden=!view.overdue&&view.last_archive_available!==false;warning.textContent=t(view.last_archive_available===false?'backupLatestUnavailable':'backupOverdue');
 }
 return {element,refresh};
}
async function backupsPage(){
 const protection=state.user.admin?backupProtectionPanel():null;
 const status=select([['','allBackupAttempts'],['verified','verified'],['running','state_running'],['failed','failed'],['interrupted','interrupted']],'');
 const kind=select([['','allBackupKinds'],...['manual','scheduled','pre_version','pre_version_test','pre_mods','pre_restore','pre_settings','pre_world','pre_world_export','pre_world_delete'].map(x=>[x,x])],'');
 const from=input('datetime-local'),until=input('datetime-local');const content=node('div'),selection=new Set(),selectedHint=node('p',{class:'hint'});let records=[],cursor='',generation=0;
 const more=button('loadMore',()=>load(false));
 function draw(){
  const deletable=new Set(records.filter(x=>x.archive_available&&!x.protected).map(x=>x.id));
  for(const id of selection)if(!deletable.has(id))selection.delete(id);
  selectedHint.textContent=t('selectedItems')+': '+selection.size+' · '+bytes(records.filter(x=>selection.has(x.id)).reduce((sum,x)=>sum+(x.size||0),0));
  const rows=records.map(x=>[node('div',{},(()=>{const check=input('checkbox');check.setAttribute('aria-label',t('selectItem')+' '+date(x.created));check.disabled=!!x.protected||!x.archive_available;check.checked=selection.has(x.id);check.addEventListener('change',()=>{if(check.checked)selection.add(x.id);else selection.delete(x.id);selectedHint.textContent=t('selectedItems')+': '+selection.size+' · '+bytes(records.filter(x=>selection.has(x.id)).reduce((sum,x)=>sum+(x.size||0),0));});return check;})(),date(x.created)),t(x.kind),bytes(x.size),node('div',{},pill(x.state,x.state==='failed'?'bad':''),pill('archive_'+x.archive_state,x.archive_available?'good':''),x.error?node('small',{text:errorText(x.error)}):null),
   node('div',{},node('span',{text:x.restore_status&&x.restore_status!=='not_tested'?t('restore_result_'+x.restore_status):'—'}),x.restore_tested?node('small',{text:date(x.restore_tested)}):null,x.restored?node('small',{text:t('restore')+': '+date(x.restored)}):null),
   x.archive_available&&state.user.admin?node('div',{class:'backup-actions',role:'group','aria-label':t('actions')},node('a',{href:'/api/backups/'+encodeURIComponent(x.id)+'/download',class:'backup-action',text:t('download')}),button('restoreTest',()=>queue('restore_test',{id:x.id}),'backup-action'),button('restore',()=>restoreBackup(x),'backup-action danger'),(()=>{const remove=button('delete',()=>deleteStoredItems('/backups/delete',[x.id],()=>load(true)),'backup-action danger');remove.disabled=!!x.protected;remove.title=x.protected?t('delete_item_protected'):'';return remove;})()):node('span',{text:x.archive_available?'—':t('archive_'+x.archive_state)})]);
  content.replaceChildren(table(['createdAt','kind','size','verification','restoreStatus','actions'],rows,'noBackups'));more.hidden=!cursor;
 }
 async function load(reset,live=false){
  const focused=live&&content.contains(document.activeElement)?document.activeElement.closest('tr')?.rowIndex:null;
  const request=reset?++generation:generation;more.disabled=true;
  const limit=live?Math.min(200,Math.max(25,records.length)):25;const oldRecords=records,oldCursor=cursor;
  const query=new URLSearchParams({state:status.value,kind:kind.value,limit:String(limit)});
  if(from.value)query.set('after',Date.parse(from.value)/1000);if(until.value)query.set('before',Date.parse(until.value)/1000);
  if(!reset&&cursor)query.set('cursor',cursor);
  try{const result=await api('/backups/history?'+query);if(request!==generation)return;const focusedId=focused?oldRecords[focused-1]?.id:null;records=reset?result.records:records.concat(result.records);cursor=result.next_cursor;if(live&&oldRecords.length>limit){const seen=new Set(records.map(x=>x.id));records=records.concat(oldRecords.slice(limit).filter(x=>!seen.has(x.id)));cursor=oldCursor;}draw();if(focusedId){const index=records.findIndex(x=>x.id===focusedId);content.querySelectorAll('input[type=checkbox]')[index]?.focus({preventScroll:true});}}finally{if(request===generation)more.disabled=false;}
 }
 for(const control of [status,kind,from,until])control.addEventListener('change',()=>attempt(()=>load(true)));
 $('page-content').replaceChildren(node('div',{},heading('backups','backupsIntro',[button('refresh',()=>load(true)),...(state.user.admin?[button('backupNow',()=>maintenanceChoice('backup',{kind:'manual'}),'primary')]:[])]),node('section',{class:'card filter-panel backup-filters'},node('div',{class:'setting-grid'},field('status',status),field('kind',kind),field('fromTime',from),field('untilTime',until)),paragraph('backupSettingsHint','hint')),node('section',{class:'card backups-card'},state.user.admin?node('div',{class:'form-actions bulk-actions'},button('selectAllDeletable',()=>{for(const x of records)if(x.archive_available&&!x.protected)selection.add(x.id);draw();}),button('deleteSelected',()=>{if(!selection.size){toast(t('selectAtLeastOne'));return;}return deleteStoredItems('/backups/delete',Array.from(selection),async()=>{selection.clear();await load(true);});},'danger'),selectedHint):null,content,more)));
 if(protection){$('page-content').prepend(protection.element);await protection.refresh();}
 await load(true);pageLiveRefresh=async()=>{if(content.isConnected&&!more.disabled){await load(true,true);if(protection)await protection.refresh();}};
}
async function eventsPage(category=state.eventView?.category||'',generation=pageRenderGeneration){
 const request=++eventsRequestGeneration;
 let records=await api('/events'+(category?'?category='+encodeURIComponent(category):''));
 if(generation!==pageRenderGeneration||request!==eventsRequestGeneration)return;
 const filter=select([['','allEvents'],['auth','auth'],['player','players'],['server','server'],['mods','mods'],['backup','backup'],['maintenance','maintenance'],['email','smtp'],['discord','discord'],['audit','audit'],['system','system']],category);
 const view=state.eventView||{query:'',from:'',until:'',page:0};state.eventView=view;view.category=category;
 filter.addEventListener('change',()=>{view.page=0;attempt(()=>eventsPage(filter.value));});
 const search=input('search',view.query,{placeholder:t('eventSearch')});
 const from=input('datetime-local',view.from);const until=input('datetime-local',view.until);const content=node('div');
 const pageSize=25,range=node('span',{class:'hint','aria-live':'polite'}),previous=button('previousPage',()=>{view.page--;draw();}),next=button('nextPage',()=>{view.page++;draw();}),pager=node('nav',{class:'form-actions event-pagination','aria-label':t('eventPages')},previous,range,next);
 function draw(){
  const query=search.value.toLocaleLowerCase();const start=from.value?Date.parse(from.value)/1000:-Infinity;const end=until.value?Date.parse(until.value)/1000:Infinity;
  const filtered=records.filter(x=>x.at>=start&&x.at<=end&&[t(x.category),t(x.event),JSON.stringify(x.data)].join(' ').toLocaleLowerCase().includes(query));
  view.page=Math.max(0,Math.min(view.page,Math.ceil(filtered.length/pageSize)-1));
  const offset=view.page*pageSize,rows=filtered.slice(offset,offset+pageSize).map(x=>[date(x.at),t(x.category),node('strong',{text:x.title||TEXT[state.language][x.event]||t('eventRecorded')}),node('div',{},node('p',{text:x.description||t('eventRecorded')}),node('details',{},node('summary',{text:t('technicalDetails')}),node('code',{class:'event-data',text:JSON.stringify({event:x.event,...x.data})})))]);
  previous.disabled=view.page===0;next.disabled=offset+pageSize>=filtered.length;range.textContent=(filtered.length?offset+1:0)+'–'+Math.min(offset+pageSize,filtered.length)+' / '+filtered.length;
  content.replaceChildren(table(['createdAt','category','event','details'],rows,'noEvents'));
 }
 [search,from,until].forEach(x=>x.addEventListener('input',()=>{view.query=search.value;view.from=from.value;view.until=until.value;view.page=0;draw();}));draw();
 $('page-content').replaceChildren(node('div',{},heading('events','eventsIntro',state.user.admin?[button('manageHistory',()=>manageEventHistory(filter.value)),node('a',{href:'/api/events/export',class:'text-button',text:t('export')})]:[]),node('section',{class:'card filter-panel event-filters'},node('div',{class:'setting-grid'},field('category',filter),field('eventSearch',search),field('fromTime',from),field('untilTime',until)),paragraph('eventWindow','hint')),node('section',{class:'card events-card'},content,pager),paragraph('humanTime','hint')));
 pageLiveRefresh=async()=>{const next=await api('/events'+(filter.value?'?category='+encodeURIComponent(filter.value):''));if(generation!==pageRenderGeneration||!content.isConnected)return;records=next;draw();};
}
async function profile(){const deliveries=await api('/notifications');const sessionPolicy=state.user.admin?await api('/auth/session-policy'):null;const notifications=state.user.notifications||{};const enabled=input('checkbox');enabled.checked=!!notifications.enabled;const categories=['auth','player','server','mods','backup','maintenance','system','user','audit'].filter(category=>state.user.admin||category!=='audit');const selected=categories.map(category=>{const checkbox=input('checkbox');checkbox.checked=(notifications.categories||[]).includes(category);return {category,checkbox};});const body=node('div',{class:'stack'},node('div',{},node('h3',{text:state.user.username}),node('p',{text:state.user.email})),node('label',{class:'checkbox-field'},enabled,t('notificationsEnabled')),paragraph('personalNotificationScope','hint'),selected.map(x=>node('label',{class:'checkbox-field'},x.checkbox,t(x.category))),button('save',async()=>{state.user.notifications={enabled:enabled.checked,categories:selected.filter(x=>x.checkbox.checked).map(x=>x.category)};await api('/profile',{language:state.language,notifications:state.user.notifications});toast(t('saved'));},'primary'),node('h3',{text:t('notificationHistory')}),deliveryHistory(deliveries),button('changePassword',()=>passwordScreen(false)),button('regenerate',async()=>{const result=await api('/auth/backup-codes',{});displayCodes(result.backup_codes,true);}),button('logout',async()=>{await api('/auth/logout',{});closeModal();state.csrf=null;loginScreen();},'danger'));body.prepend(factorPanel());body.append(await rememberedSessionsPanel());if(sessionPolicy)body.prepend(sessionPolicyPanel(sessionPolicy));modal('profile',body);}
function settingsConnectionTest(label,path,feedback,success){
 return button(label,async()=>{
  feedback.hidden=false;
  const owner=feedback.closest('form');
  const dirty=settingsDraftState&&Array.from(settingsDraftState.baselines).some(([control,before])=>owner?.contains(control)&&draftValue(control)!==before);
  if(dirty){feedback.className='connection-test-result warning-box';feedback.textContent=t('saveBeforeConnectionTest');return;}
  feedback.className='connection-test-result info-box';feedback.textContent=t('connectionTestRunning');
  try{await api(path,{});feedback.className='connection-test-result success-box';feedback.textContent=t(success);toast(t(success));}
  catch(error){feedback.className='connection-test-result warning-box';feedback.textContent=errorText(error.code);throw error;}
 });
}

async function settings(initialCategory='',focus='',options={}){const cfg=await api('/settings');const holder=node('div',{class:'settings-card-grid'});holder.append(...await Promise.all([runtimeSettings(),serverPropertiesSettings(),worldSettings(),minecraftPermissionsSettings(),gameRulesSettings()]));function section(title,intro,body){holder.append(node('section',{class:'setting-section'},node('h3',{text:t(title)}),paragraph(intro),body));}const smtp=cfg.smtp;const host=input('text',smtp.host,{required:true,maxLength:253});const port=input('number',smtp.port,{required:true,min:1,max:65535});const security=select([['starttls','STARTTLS'],['tls','TLS']],smtp.security);const username=input('email',smtp.username,{required:true,maxLength:254});const sender=input('email',smtp.sender,{required:true,maxLength:254});const password=input('password','',{autocomplete:'new-password',placeholder:t(smtp.password_configured?'passwordConfigured':'passwordMissing'),maxLength:1000});const mailTestFeedback=node('p',{class:'connection-test-result',role:'status','aria-live':'polite',hidden:true});section('smtp','smtpIntro',form([node('div',{class:'setting-grid'},field('host',host),field('port',port),field('security',security),field('username',username),field('sender',sender),field('password',password)),settingsConnectionTest('testMail','/settings/smtp/test',mailTestFeedback,'smtpAccepted'),mailTestFeedback],'save',async()=>{await api('/settings',{section:'smtp',value:{host:host.value,port:Number(port.value),security:security.value,username:username.value,sender:sender.value,password:password.value}});password.value='';toast(t('saved'));}));
const providerKey=input('password','',{autocomplete:'new-password',maxLength:1000,placeholder:t(cfg.providers.curseforge_api_key_configured?'passwordConfigured':'passwordMissing')});
section('providers','providersIntro',form([field('curseforgeApiKey',providerKey)],'save',async()=>{await api('/settings',{section:'providers',value:{curseforge_api_key:providerKey.value}});providerKey.value='';toast(t('saved'));}));
const discordEnabled=input('checkbox');discordEnabled.checked=cfg.discord.enabled;
const webhook=input('password','',{placeholder:t(cfg.discord.webhook_configured?'passwordConfigured':'passwordMissing'),autocomplete:'new-password',maxLength:1000});
let savedWebhookConfigured=!!cfg.discord.webhook_configured;
const webhookPreview=node('code',{class:'webhook-preview',hidden:true,tabIndex:0,'aria-label':t('webhook')});
const copyWebhook=button('copyWebhook',async()=>{await navigator.clipboard.writeText(webhookPreview.textContent);toast(t('copied'));});copyWebhook.disabled=true;
function hideWebhook(){webhook.type='password';webhookPreview.textContent='';webhookPreview.hidden=true;copyWebhook.disabled=true;showWebhook.querySelector('span').textContent=t('showWebhook');}
const showWebhook=button('showWebhook',async()=>{
 if(!webhookPreview.hidden){hideWebhook();return;}
 let value=webhook.value;
 if(!value&&savedWebhookConfigured)value=(await api('/settings/discord/webhook/reveal',{})).webhook;
 if(!value){toast(t('discord_webhook_required'));return;}
 webhook.type='text';webhookPreview.textContent=value;webhookPreview.hidden=false;copyWebhook.disabled=false;showWebhook.querySelector('span').textContent=t('hideWebhook');
});
webhook.addEventListener('input',()=>{if(!webhookPreview.hidden){if(webhook.value)webhookPreview.textContent=webhook.value;else hideWebhook();}});
const webhookActions=node('div',{class:'webhook-actions'},node('div',{class:'form-actions'},showWebhook,copyWebhook),webhookPreview);
const greetingConfig=cfg.greetings||{first_enabled:false,return_enabled:false,first_message:'Willkommen auf dem Server, {player}!',return_message:'Willkommen zurück, {player}!'};
const firstGreeting=input('checkbox');firstGreeting.checked=!!greetingConfig.first_enabled;
const returnGreeting=input('checkbox');returnGreeting.checked=!!greetingConfig.return_enabled;
const firstGreetingText=input('text',greetingConfig.first_message,{maxLength:500,required:true});
const returnGreetingText=input('text',greetingConfig.return_message,{maxLength:500,required:true});
section('greetings','greetingsIntro',form([paragraph('greetingsPlaceholder','info-box'),node('label',{class:'checkbox-field'},firstGreeting,t('firstGreetingEnabled')),field('firstGreetingMessage',firstGreetingText),node('label',{class:'checkbox-field'},returnGreeting,t('returnGreetingEnabled')),field('returnGreetingMessage',returnGreetingText)],'save',async()=>{await api('/settings',{section:'greetings',value:{first_enabled:firstGreeting.checked,return_enabled:returnGreeting.checked,first_message:firstGreetingText.value,return_message:returnGreetingText.value}});toast(t('saved'));}));
const discordLanguage=select([['de','Deutsch'],['en','English']],cfg.discord.language||'de');
const discordEvents=['status','auth','player','server','mods','backup','maintenance','system','user','audit'].map(category=>{const checkbox=input('checkbox');checkbox.checked=(cfg.discord.events||[]).includes(category);return {category,checkbox};});
async function saveDiscord(){await api('/settings',{section:'discord',value:{enabled:discordEnabled.checked,webhook:webhook.value,events:discordEvents.filter(x=>x.checkbox.checked).map(x=>x.category),language:discordLanguage.value}});savedWebhookConfigured=savedWebhookConfigured||!!webhook.value;webhook.value='';webhook.placeholder=t(savedWebhookConfigured?'passwordConfigured':'passwordMissing');hideWebhook();toast(t('saved'));}
const discordTestFeedback=node('p',{class:'connection-test-result',role:'status','aria-live':'polite',hidden:true});section('discord','discordIntro',form([node('h4',{text:t('discordConnection')}),node('label',{class:'checkbox-field'},discordEnabled,t('discordEnabled')),field('webhook',webhook),webhookActions,field('language',discordLanguage),settingsConnectionTest('testDiscord','/settings/discord/test',discordTestFeedback,'discordTestSent'),discordTestFeedback,node('h4',{text:t('discordEvents')}),paragraph('discordEventsIntro','hint'),...discordEvents.map(x=>node('label',{class:'checkbox-field'},x.checkbox,t(x.category==='status'?'discordStatus':x.category)))],'save',saveDiscord));const auto=input('checkbox');auto.checked=!!cfg.maintenance.automatic;
const enabled=input('checkbox');enabled.checked=cfg.maintenance.backup_enabled;
const check=input('number',cfg.maintenance.check_minutes,{min:5,max:1440,required:true});
const backup=input('number',cfg.maintenance.backup_minutes,{min:5,max:1440,required:true});
const retention=input('number',cfg.maintenance.retention_days,{min:1,max:90,required:true});
const folderScan=input('checkbox');folderScan.checked=cfg.maintenance.folder_scan_enabled!==false;
const folderAutomatic=input('checkbox');folderAutomatic.checked=!!cfg.maintenance.folder_automatic;
const folderCheck=input('number',cfg.maintenance.folder_check_minutes??30,{min:5,max:1440,required:true});
section('schedules','automaticIntro',form([
 node('label',{class:'checkbox-field'},auto,t('automaticMods')),field('checkMinutes',check),
 node('h4',{text:t('folderScanEnabled')}),node('label',{class:'checkbox-field'},folderScan,t('folderScanEnabled')),
 field('folderCheckMinutes',folderCheck),node('label',{class:'checkbox-field'},folderAutomatic,t('folderAutomatic')),paragraph('folderAutomaticHint','info-box'),
 node('h4',{text:t('backups')}),node('label',{class:'checkbox-field'},enabled,t('backupEnabled')),
 node('div',{class:'setting-grid'},field('backupMinutes',backup),field('retentionDays',retention)),paragraph('backupTimingHint','info-box')
],'save',async()=>{
 await api('/settings',{section:'maintenance',value:{automatic:auto.checked,backup_enabled:enabled.checked,check_minutes:Number(check.value),backup_minutes:Number(backup.value),retention_days:Number(retention.value),folder_scan_enabled:folderScan.checked,folder_check_minutes:Number(folderCheck.value),folder_automatic:folderAutomatic.checked}});
 toast(t('saved'));
}));
const users=await api('/users');section('users','webUsersIntro',node('div',{},users.map(x=>node('div',{class:'list-row'},node('div',{},node('strong',{text:x.username}),node('small',{text:x.email})),pill(x.admin?'admin':'user'),pill(x.enabled?'userEnabled':'userDisabled'),node('div',{class:'form-actions'},button('editUser',()=>manageUser(x)),(()=>{const remove=button('deleteUser',()=>deleteWebUser(x),'danger');remove.disabled=x.id===state.user.id||!!x.admin&&!!x.enabled&&users.filter(u=>u.admin&&u.enabled).length<=1;remove.title=remove.disabled?t(x.id===state.user.id?'cannot_delete_own_user':'last_admin_required'):'';return remove;})()))),button('addUser',addUser),button('sessionPolicy',profile)));holder.append(infrastructureSettings(cfg),applicationUpdateSettings(cfg.application_update));section('changelog','v100',paragraph('firstRelease'));prepareSettingsNavigation(holder,initialCategory);holder.dataset.initialFocus=focus;modal('settings',holder,options);}
function addUser(){const username=input('text','',{required:true,pattern:'[A-Za-z0-9_.\\-]{2,40}',maxLength:40});const email=input('email','',{required:true,maxLength:254});const admin=input('checkbox');modal('addUser',form([field('username',username),field('email',email),node('label',{class:'checkbox-field'},admin,t('admin'))],'addUser',async()=>{const result=await api('/users',{username:username.value,email:email.value,admin:admin.checked,language:state.language});modal('initialPassword',node('div',{},paragraph('initialPasswordHint'),node('div',{class:'secret',text:result.initial_password}),button('close',closeModal)));}));}
$('modal-close').addEventListener('click',closeModal);$('modal').addEventListener('cancel',event=>{event.preventDefault();closeModal();});$('modal').addEventListener('close',()=>{if(!$('modal').open)$('modal-content').replaceChildren();});$('settings-button').addEventListener('click',()=>attempt(settings));$('profile-button').addEventListener('click',()=>attempt(profile));document.querySelectorAll('[data-page]').forEach(element=>element.addEventListener('click',()=>attempt(async()=>{state.page=element.dataset.page;await renderPage();window.scrollTo(0,0);document.querySelector('.workspace').scrollTop=0;})));$('language').addEventListener('change',()=>attempt(async()=>{state.language=$('language').value;localStorage.setItem('mcj-language',state.language);translate();if(state.user){if($('application').hidden)await api('/auth/language',{language:state.language});else await api('/profile',{language:state.language,notifications:state.user.notifications||{}});state.user.language=state.language;if(!$('application').hidden)await renderPage();}else loginScreen();}));
function openSecurityLink(){const hash=location.hash;if(hash.startsWith('#recover=')){history.replaceState(null,'','/');factorRecoveryScreen(hash.slice(9));return true;}if(hash.startsWith('#reset=')){history.replaceState(null,'','/');resetScreen(hash.slice(7));return true;}return false;}
window.addEventListener('hashchange',openSecurityLink);
document.querySelectorAll('.cube').forEach(x=>x.replaceChildren(icon('brand')));document.querySelectorAll('[data-page]').forEach(x=>{const slot=x.firstElementChild;slot.setAttribute('aria-hidden','true');slot.replaceChildren(icon(x.dataset.page));});$('settings-button').replaceChildren(icon('settings'));
translate();if(!openSecurityLink())attempt(async()=>{try{await continueAuthentication();}catch{loginScreen();}});
async function refreshVisiblePage(){
 if(pageLiveBusy||!state.user||$('application').hidden||document.querySelector('.reauth-dialog')||document.hidden)return;
 pageLiveBusy=true;try{if(state.page==='overview'&&overviewLiveRefresh)await overviewLiveRefresh();else if(pageLiveRefresh)await pageLiveRefresh();}finally{pageLiveBusy=false;}
}
setInterval(()=>attempt(refreshVisiblePage),5000);
window.addEventListener('focus',()=>attempt(refreshVisiblePage));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)attempt(refreshVisiblePage);});

function factorRecoveryScreen(token){
 const password=input('password','',{required:true,autocomplete:'current-password',maxLength:128});
 authBody('factorRecovery',form([paragraph('factorRecoveryIntro'),field('currentPassword',password)],'recoverFactor',async()=>{
  await api('/auth/recovery/complete',{token,password:password.value});password.value='';token='';loginScreen();toast(t('factorRecoveryComplete'));
 }));
}

function deleteWebUser(user){
 const confirmation=input('text','',{required:true,autocomplete:'off',maxLength:40});
 const body=form([paragraph('deleteUserHint'),node('strong',{text:user.username}),field('deleteUserConfirmation',confirmation)],'deleteUser',async()=>{
  if(confirmation.value!==user.username){confirmation.setCustomValidity(t('user_delete_confirmation_required'));confirmation.reportValidity();return;}
  await api('/users/'+user.id+'/delete',{confirmation:confirmation.value});await settings('users');toast(t('userDeleted'));
 });body.querySelector('button[type=submit]').classList.remove('primary');body.querySelector('button[type=submit]').classList.add('danger');confirmation.addEventListener('input',()=>confirmation.setCustomValidity(''));modal('deleteUser',body);
}

function manageUser(user){
 const username=input('text',user.username,{required:true,pattern:'[A-Za-z0-9_.\\-]{2,40}',maxLength:40});
 const email=input('email',user.email,{required:true,maxLength:254});
 const language=select([['de','Deutsch'],['en','English']],user.language);
 const admin=input('checkbox');admin.checked=!!user.admin;
 const enabled=input('checkbox');enabled.checked=!!user.enabled;
 const body=form([field('username',username),field('email',email),field('language',language),
  node('label',{class:'checkbox-field'},admin,t('admin')),node('label',{class:'checkbox-field'},enabled,t('userEnabled')),
  paragraph('userEditSessionHint','hint')],'save',async()=>{
   const result=await api('/users/'+user.id,{username:username.value,email:email.value,language:language.value,admin:admin.checked,enabled:enabled.checked});
   if(result.login_required){closeModal();loginScreen();toast(t('loginAgain'));}else await settings();
  });
 if(user.factor&&user.enabled&&user.id!==state.user.id)body.append(button('factorRecovery',async()=>{
  if(!confirm(t('factorRecoveryConfirm')))return;
  await api('/users/'+user.id+'/recovery',{});toast(t('factorRecoverySent'));
 }));
 modal('editUser',body);
}

async function worldSettings(){
 const data=await api('/worlds');const section=node('section',{class:'setting-section'},node('h3',{text:t('worldManagement')}),paragraph('worldIntro'));
 const names=new Set();
 for(const world of [...data.worlds,...data.imports]){
  if(names.has(world.name))continue;names.add(world.name);const active=world.name===data.current;
  const controls=node('div',{class:'form-actions'});
  if(!active)controls.append(button('activateWorld',()=>maintenanceChoice('world_change',{name:world.name,create:world.source!=='server'}),'primary'));
  if(world.source==='server')controls.append(button('exportWorld',()=>maintenanceChoice('world_export',{name:world.name})));
  const remove=button('deleteWorld',()=>confirmAction('deleteWorldConfirm',()=>maintenanceChoice('world_delete',{name:world.name})),'danger');remove.disabled=active||world.source!=='server';remove.title=active?t('active_world_protected'):'';controls.append(remove);
  section.append(node('div',{class:'list-row world-row'},node('div',{},node('strong',{text:world.name}),node('small',{text:(active?t('activeWorld'):world.source==='server'?t('existingWorld'):t('stagedWorld'))+' · '+(world.size_complete===false?'≥ ':'')+bytes(world.size)}),node('small',{},t('usedWorldSeed')+': ',node('code',{text:typeof world.seed==='string'&&/^-?\d{1,19}$/.test(world.seed)?world.seed:t('worldSeedUnavailable')}))),active?pill('activeWorld','good'):null,controls));
 }
 section.append(paragraph('usedWorldSeedHint','hint'));
 const name=input('text','',{required:true,pattern:'[A-Za-z0-9_\\-]{1,60}',maxLength:60}),archive=input('file','',{accept:'.zip,application/zip'}),seed=input('text','',{maxLength:200}),kind=select([['minecraft:normal','worldNormal'],['minecraft:flat','worldFlat'],['minecraft:large_biomes','worldLargeBiomes'],['minecraft:amplified','worldAmplified']],'minecraft:normal'),structures=input('checkbox'),generator=input('text','',{maxLength:4000,placeholder:'{}'});structures.checked=true;
 section.append(form([node('h4',{text:t('createWorld')}),field('worldName',name),paragraph('worldNameHint','hint'),node('div',{class:'setting-grid'},field('worldSeed',seed),field('worldType',kind)),node('label',{class:'checkbox-field'},structures,t('worldStructures')),field('worldGeneratorSettings',generator),field('worldArchive',archive),paragraph('worldArchiveHint','hint')],'createOrImportWorld',async()=>{
  if(names.has(name.value)){toast(t('world_name_already_exists'));return;}
  if(archive.files.length){await api('/worlds/upload?name='+encodeURIComponent(name.value),archive.files[0]);archive.value='';maintenanceChoice('world_change',{name:name.value,create:true});return;}
  let value={};try{value=JSON.parse(generator.value||'{}');if(!value||typeof value!=='object'||Array.isArray(value))throw Error();}catch{toast(t('invalidGeneratorSettings'));return;}
  maintenanceChoice('world_change',{name:name.value,create:true,generation:{'level-seed':seed.value,'level-type':kind.value,'generate-structures':String(structures.checked),'generator-settings':JSON.stringify(value)}});
 }));
 if(data.exports?.length)section.append(node('h4',{text:t('worldExports')}),...data.exports.map(item=>node('div',{class:'list-row'},node('span',{text:item.name+' · '+date(item.created)+' · '+bytes(item.size)}),node('a',{class:'text-button',href:'/api/worlds/exports/'+item.id+'/download',text:t('download')}))));
 return section;
}

async function minecraftPermissionsSettings(){
 const cfg=await api('/players/permissions');const section=node('section',{class:'setting-section'},node('h3',{text:t('minecraftPermissions')}),paragraph('minecraftPermissionsIntro'),paragraph('visitorPermissionsFixed','hint'));
 if(cfg.error)section.append(errorParagraph(cfg.error,'warning-box'));
 if(!cfg.supported)section.append(paragraph('permission_adapter_not_available','warning-box'));
 const controls={},roleCards=[];const groups=['player','moderator','administrator'];
 const editor=form(groups.map(group=>{
  controls[group]=cfg.abilities.map(ability=>{const checkbox=input('checkbox');checkbox.checked=(cfg.roles[group]||[]).includes(ability);checkbox.disabled=!cfg.supported;return {ability,checkbox};});
  const card=node('div',{class:'card permission-role-card','data-role':group},node('h4',{text:t(group)}),controls[group].map(x=>node('label',{class:'checkbox-field'},x.checkbox,t('mcPermission_'+x.ability))));roleCards.push(card);return card;
 }),'save',async()=>{
  const roles={visitor:[]};for(const group of groups)roles[group]=controls[group].filter(x=>x.checkbox.checked).map(x=>x.ability);
  await api('/players/permissions',{roles});toast(t('saved'));
 });
 editor.querySelector('button[type="submit"]').disabled=!cfg.supported;
 const tabs=node('div',{class:'permission-role-tabs',role:'group','aria-label':t('minecraftPermissions')});function showRole(group){for(const card of roleCards)card.hidden=card.dataset.role!==group;for(const tab of tabs.children)tab.setAttribute('aria-pressed',String(tab.dataset.role===group));}for(const group of groups)tabs.append(node('button',{type:'button','data-role':group,text:t(group),onclick:()=>showRole(group)}));showRole('player');section.append(tabs,editor,paragraph('minecraftPermissionCommands','hint'));return section;
}

async function runtimeSettings(draft=null,wizard=false){
 let data=await api('/versions');
 if(wizard&&!data.catalog?.releases?.length){
  try{await api('/versions/check',{});data=await api('/versions');}catch{}
 }
 const current=data.current;const catalog=data.catalog;
 const supported=(data.compatibility?.variants||[]).filter(x=>x.selectable===true&&x.loader_versions.length);
 const section=node('section',{class:'setting-section'},node('h3',{text:t('runtimeSettings')}),paragraph('runtimeIntro'));
 section.append(node('div',{class:'info-box',text:current.version+' · Java '+(current.java||25)+' · '+current.loader+' '+current.loader_version}));
 const refreshButton=button('findStableVersions',async()=>{await api('/versions/check',{});const replacement=await runtimeSettings({version:minecraft.value,java:Number(java.value),loader:loader.value,loader_version:loader.value==='NEOFORGE'?loaderVersion.value:manualVersion.value,properties:{'level-name':versionWorld.value}},wizard);decorateSettingsPanel(replacement,'runtimeSettings','server');replacement.hidden=section.hidden;section.replaceWith(replacement);});
 section.append(refreshButton);
 if(wizard&&!data.catalog?.releases?.length)section.append(paragraph('setupVersionCatalogUnavailable','info-box'));
 const selectedMinecraft=draft?.version||current.version,selectedLoader=draft?.loader||current.loader;const releases=Array.from(new Map([...(catalog?.releases||[]),{id:current.version},{id:selectedMinecraft}].map(x=>[x.id,x])).values());
 const minecraft=node('select',{},releases.map(x=>node('option',{value:x.id,text:x.id,selected:x.id===selectedMinecraft})));
 const java=node('select',{},[17,21,25].map(x=>node('option',{value:String(x),text:'Java '+x,selected:x===(draft?.java||current.java||25)})));
 const loader=node('select',{},['FABRIC','FORGE','NEOFORGE'].map(x=>node('option',{value:x,text:x,selected:x===selectedLoader})));
 const versionWorld=input('text',draft?.properties?.['level-name']||(selectedMinecraft===current.version?current.world||'world':'world_'+selectedMinecraft.replaceAll('.','_')),{required:true,maxLength:60,pattern:'[A-Za-z0-9_-]{1,60}'});let worldTouched=!!draft?.properties;
 versionWorld.addEventListener('input',()=>{worldTouched=true;});
 if(data.compatibility){
  section.append(paragraph('runtimeSupportHint','info-box'));
  for(const option of minecraft.options){option.disabled=!supported.some(x=>x.minecraft===option.value);if(option.disabled)option.textContent+=' · '+t('runtimeNotSupported');}
 }
 function reflectSupportedCombination(){
  if(!data.compatibility)return;
  const variants=supported.filter(x=>x.minecraft===minecraft.value);
  for(const option of loader.options){option.disabled=!variants.some(x=>x.loader===option.value);option.textContent=option.value+(option.disabled?' · '+t('runtimeNotSupported'):'');}
  if(loader.selectedOptions[0]?.disabled&&variants.length)loader.value=variants[0].loader;
  const choices=variants.filter(x=>x.loader===loader.value);
  for(const option of java.options){option.disabled=!choices.some(x=>String(x.java)===option.value);option.textContent='Java '+option.value+(option.disabled?' · '+t('runtimeNotSupported'):'');}
  if(java.selectedOptions[0]?.disabled&&choices.length)java.value=String(choices[0].java);
 }
 reflectSupportedCombination();
 minecraft.setAttribute('aria-label',t('minecraftVersion'));java.setAttribute('aria-label',t('javaVersion'));loader.setAttribute('aria-label',t('modloader'));
 const loaderVersion=node('select',{'aria-label':t('loaderVersion'),required:true});
 const versionControl=node('div',{class:'loader-version-control'}),loaderNotice=node('small',{class:'hint'});
 let versionRequest=0;const selectedNeoForge=new Map([[current.version,current.loader==='NEOFORGE'?current.loader_version:'']]);if(draft?.loader==='NEOFORGE')selectedNeoForge.set(draft.version,draft.loader_version);
 let manualVersion=input('text',selectedLoader==='NEOFORGE'?'':draft?.loader_version||current.loader_version,{maxLength:40,placeholder:t('stableLoaderAutomatic')});
 loaderVersion.addEventListener('change',()=>selectedNeoForge.set(minecraft.value,loaderVersion.value));
 async function loadNeoForge(){
  const generation=++versionRequest,chosenMinecraft=minecraft.value;
  versionControl.replaceChildren(loader.value==='NEOFORGE'?loaderVersion:manualVersion,loaderNotice);
  if(loader.value!=='NEOFORGE'){versionControl.replaceChildren(manualVersion);return;}
  versionControl.replaceChildren(loaderVersion,loaderNotice);loaderVersion.disabled=true;loaderNotice.textContent=t('loaderVersionsLoading');
  const tested=supported.find(x=>x.minecraft===chosenMinecraft&&x.loader===loader.value&&x.java===Number(java.value));
  const selected=selectedNeoForge.get(chosenMinecraft)||tested?.loader_versions[0]||'';
  loaderVersion.replaceChildren(node('option',{value:selected,text:selected||t('selectLoaderVersion')}));
  try{const catalog=await api('/versions/neoforge?minecraft='+encodeURIComponent(chosenMinecraft));if(generation!==versionRequest)return;
   const versions=Array.from(new Set([...(selected?[selected]:[]),...catalog.versions]));
   loaderVersion.replaceChildren(node('option',{value:'',text:t('selectLoaderVersion')}),...versions.map(value=>{const unsupported=!!data.compatibility&&!tested?.loader_versions.includes(value);return node('option',{value,text:value+(unsupported?' · '+t('runtimeNotSupported'):''),selected:value===selected,disabled:unsupported});}));
   loaderVersion.value=selected;loaderNotice.textContent=catalog.versions.length?t('loaderVersionsVerified')+' · '+date(catalog.checked):t('loaderVersionsNone');
  }catch(error){if(generation!==versionRequest)return;loaderNotice.textContent=t('loader_catalog_unavailable');}
  finally{if(generation===versionRequest)loaderVersion.disabled=false;}
 }
 minecraft.addEventListener('change',()=>{if(!worldTouched)versionWorld.value=minecraft.value===current.version?current.world||'world':'world_'+minecraft.value.replaceAll('.','_');reflectSupportedCombination();return loadNeoForge();});loader.addEventListener('change',()=>{reflectSupportedCombination();return loadNeoForge();});java.addEventListener('change',loadNeoForge);await loadNeoForge();
 const result=node('div',{class:'validation-result','aria-live':'polite'},paragraph('noCheckResult'));

 section.append(form([node('div',{class:'setting-grid'},field('minecraftVersion',minecraft),field('javaVersion',java),field('modloader',loader),field('loaderVersion',versionControl),field('versionWorld',versionWorld)),paragraph('versionWorldHelp','hint')],
  'checkConfiguration',async()=>{if(loader.value==='NEOFORGE'&&(loaderVersion.disabled||!loaderVersion.value)){toast(t('selectLoaderVersion'));return;}await requestVersionPlan(result,{version:minecraft.value,java:Number(java.value),loader:loader.value,loader_version:loader.value==='NEOFORGE'?loaderVersion.value:manualVersion.value,properties:{'level-name':versionWorld.value}});}),result);
 if(catalog)section.append(node('small',{text:t('lastChecked')+': '+date(catalog.checked)+' · '+t('latestStable')+': '+catalog.latest_stable}));
 if(!wizard)section.append(button('openVersionHistory',()=>openVersionHistory(section)));section.append(paragraph('explicitVersionsOnly','hint'));
 if(wizard)return section;
 const local=node('details',{id:'local-runtime-files',open:true},node('summary',{text:t('localRuntimeFiles')}));
 const localContent=node('div');local.append(paragraph('localRuntimeCopiesHint','hint'),localContent);section.append(local);
 local.addEventListener('toggle',()=>{if(!local.open)return;attempt(async()=>{const value=await api('/versions/local');localContent.replaceChildren(runtimeCleanupControls(value.cleanup,value.cleanup_last),table(['version','size','status','actions'],value.files.map(item=>[item.kind+' '+item.version,bytes(item.size),node('div',{},pill('runtimeFile_'+item.status,item.status==='active'?'good':''),item.independent_rollback_copies?node('small',{text:t('independentRuntimeCopy')}):null),item.deletable?button('delete',async()=>{const preview=await api('/versions/local/delete',{id:item.id});modal('delete',node('div',{class:'stack'},node('p',{text:item.kind+' '+item.version+' · '+bytes(preview.bytes)}),paragraph('localRuntimeDeleteWarning'),button('delete',async()=>{await api('/versions/local/delete',{id:item.id,confirmation:preview.confirmation});closeModal();toast(t('deletionComplete'));await settings('runtimeSettings');},'danger')));}):null]),'noLocalRuntimeFiles'));});});
 return section;
}

function runtimeCleanupControls(policy={},last=null){
 const enabled=input('checkbox');enabled.checked=!!policy?.enabled;const days=input('number',policy?.retention_days??14,{min:1,max:365,required:true});
 const lastCheck=node('p',{class:'hint',text:last?t('runtimeCleanupLast')+': '+date(last.checked_at)+' · '+last.count+' '+t('runtimeCleanupRemoved')+' · '+bytes(last.bytes):t('runtimeCleanupNever')});
 const editor=form([node('label',{class:'checkbox-field'},enabled,t('runtimeCleanupEnabled')),field('runtimeCleanupDays',days)],'save',async()=>{await api('/versions/local/cleanup-policy',{enabled:enabled.checked,retention_days:Number(days.value)});markSettingsFormSaved(editor);toast(t('saved'));});
 return node('section',{class:'runtime-cleanup stack'},node('h4',{text:t('runtimeCleanupTitle')}),paragraph('runtimeCleanupHint','hint'),editor,lastCheck);
}

async function serverPropertiesSettings(){
 const data=await api('/server/settings');
 const section=node('section',{class:'setting-section'},node('h3',{text:t('serverProperties')}),paragraph('propertiesIntro'));
 const search=input('search','',{id:'server-property-search',placeholder:t('propertySearch'),'aria-describedby':'server-property-search-help'}),searchStatus=node('small',{class:'hint',role:'status','aria-live':'polite'}),searchEmpty=paragraph('propertySearchEmpty','info-box');const fields=[];let favorites=new Set(data.ui_preferences?.favorite_properties||[]),favoritesSaving=false;
 const list=node('div',{class:'stack property-list'}),groups=new Map(),favoriteGroup=node('fieldset',{class:'property-group property-favorites'},node('legend',{text:t('favoriteProperties')}));list.append(favoriteGroup);const result=node('div',{class:'validation-result','aria-live':'polite'},paragraph('noCheckResult'));
 for(const [key,value] of Object.entries(data.properties).sort(([a],[b])=>a.localeCompare(b))){
  const locked=data.protected.includes(key)||key==='level-name';let control;const initial=pendingSettingsChanges&&pendingSettingsChanges.basis===data.basis?(pendingSettingsChanges.changes.properties[key]??value):value;
  if(['true','false'].includes(value)){control=input('checkbox');control.checked=String(initial)==='true';}
  else control=input('text',initial,{maxLength:4000});
  control.disabled=locked;
  const help=serverPropertyHelp(key),helpId='property-help-'+key;control.setAttribute('aria-describedby',helpId);
  const row=node('label',{class:control.type==='checkbox'?'checkbox-field':'field'},node('span',{text:key}),control,node('small',{id:helpId,class:'property-help',text:help}),locked?node('small',{text:t('protectedProperty')}):null);
  const group=/^(view-distance|simulation-distance|max-tick-time|sync-chunk-writes|network-compression-threshold|region-file-compression)/.test(key)?'propertyPerformance':/^(level-|generate-|generator-|initial-)/.test(key)?'propertyWorld':/^(server-|enable-|query|rcon|management-|resource-pack|accepts-transfers|prevent-proxy|rate-limit|use-native)/.test(key)?'propertyConnection':'propertyGameplay';
  if(!groups.has(group)){const body=node('fieldset',{class:'property-group'},node('legend',{text:t(group)}));groups.set(group,body);list.append(body);}
  const star=button('markPropertyFavorite',async()=>{if(favoritesSaving)return;favoritesSaving=true;fields.forEach(x=>x.star.disabled=true);try{const next=new Set(favorites);if(next.has(key))next.delete(key);else next.add(key);const saved=await api('/profile/ui-preferences',{favorite_properties:Array.from(next)});favorites=new Set(saved.favorite_properties);placeFavorites();}finally{favoritesSaving=false;fields.forEach(x=>x.star.disabled=false);}});star.classList.add('property-favorite');
  const entry=node('div',{class:'property-entry','data-property':key},row,star);fields.push({key,help,control,row:entry,label:row,locked,group,star});groups.get(group).append(entry);
 }
 function filterProperties(){const words=search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);let count=0;for(const x of fields){const text=[x.key,x.help].join(' ').toLocaleLowerCase();x.row.hidden=!words.every(word=>text.includes(word));if(!x.row.hidden)count++;}for(const group of [...groups.values(),favoriteGroup])group.hidden=!Array.from(group.querySelectorAll('.property-entry')).some(x=>!x.hidden);searchStatus.textContent=t('propertySearchMatches')+': '+count+' / '+fields.length;searchEmpty.hidden=count!==0;}
 function placeFavorites(){for(const x of fields){const favorite=favorites.has(x.key);(favorite?favoriteGroup:groups.get(x.group)).append(x.row);x.star.querySelector('span').textContent=favorite?'★':'☆';const label=t(favorite?'unmarkPropertyFavorite':'markPropertyFavorite')+': '+x.key;x.star.setAttribute('aria-label',label);x.star.title=label;x.star.setAttribute('aria-pressed',String(favorite));}filterProperties();}
 search.addEventListener('input',filterProperties);placeFavorites();
 const currentMemory=data.memory?.container_memory_mb??data.current.container_memory_mb??8192;const pendingMemory=pendingSettingsChanges&&pendingSettingsChanges.basis===data.basis?pendingSettingsChanges.changes.container_memory_mb:null;const memory=input('number',(pendingMemory??currentMemory)/1024,{min:4,max:Math.max(currentMemory/1024,Math.floor((data.memory?.maximum_mb??65536)/1024)),step:1,required:true,disabled:!data.memory});const memoryHint=node('p',{class:'memory-allocation-summary'});function memoryPreview(){memoryHint.textContent=data.memory?t('memoryJavaBudget')+': '+Math.max(1,Number(memory.value)-2)+' GiB · '+t('memoryHostReserve')+': '+decimal(data.memory.host_reserve_mb/1024)+' GiB':t('host_memory_unavailable');}memory.addEventListener('input',memoryPreview);memoryPreview();
 function editedChanges(){const properties={};for(const x of fields)if(!x.locked&&x.key!=='level-name'){const value=x.control.type==='checkbox'?String(x.control.checked):x.control.value;if(value!==String(data.properties[x.key]))properties[x.key]=value;}const changes={properties};if(!memory.disabled&&Number(memory.value)*1024!==currentMemory)changes.container_memory_mb=Number(memory.value)*1024;return changes;}
 function hasChanges(changes){return Object.keys(changes.properties).length||changes.memory_mb!==undefined||changes.container_memory_mb!==undefined;}
 const collect=button('collectChanges',()=>{if(!body.reportValidity())return;const changes=editedChanges();if(!hasChanges(changes)){toast(t('settings_unchanged'));return;}pendingSettingsChanges={changes,basis:data.basis};markSettingsFormSaved(body);updateChangeBasket();closeModal();toast(t('settingsChangesCollected'));});
 const body=form([node('div',{class:'stack property-search'},node('label',{for:'server-property-search',text:t('propertySearch')}),search,node('small',{id:'server-property-search-help',class:'hint',text:t('propertySearchHint')}),searchStatus),field('containerMemoryBudget',memory),memoryHint,paragraph('memoryContainerHint','hint'),searchEmpty,list,paragraph('propertyRestartHint','hint'),collect],'applyServerSettings',async()=>{
  const changes=editedChanges();if(!hasChanges(changes)){toast(t('settings_unchanged'));return;}maintenanceChoice('server_settings',{changes,basis:data.basis,_collected_settings:!!pendingSettingsChanges&&pendingSettingsChanges.basis===data.basis,_settings_form_review:true});
 });
 section.append(body,result);return section;
}

async function clientPackPanel(){
 const section=node('section',{class:'card client-pack-panel'},node('div',{class:'card-head'},node('div',{},node('h3',{},icon('mods'),t('clientPackTitle')),paragraph('clientPackIntro','hint')))),body=node('div',{class:'card-body stack'});let data;
 try{data=await api('/client-packs');}catch(error){if(error.code!=='maintenance_busy')throw error;body.append(paragraph('maintenance_busy','info-box'),node('div',{class:'form-actions'},button('allMaintenanceJobs',openMaintenance),button('refresh',renderPage)));section.append(body);return section;}
 const selected=new Set(),bulkHint=node('p',{class:'hint'});
 const build=button('clientPackBuild',async()=>{build.disabled=true;try{const job=await api('/client-packs/build',{});toast(t('clientPackBuilding'));const until=Date.now()+300000;while(Date.now()<until){await new Promise(resolve=>setTimeout(resolve,2000));const jobs=await api('/jobs'),value=jobs.find(x=>x.id===job.id);if(value&&['succeeded','failed','blocked','interrupted'].includes(value.state)){toast(t(value.state==='succeeded'?'clientPackBuilt':'clientPackBuildFailed'));if(state.page==='mods')await renderPage();return;}if(state.page!=='mods')return;}toast(t('clientPackBuilding'));}finally{build.disabled=false;}},'primary');
 body.append(paragraph('clientPackVersionHint','hint'));
 body.append(node('div',{class:'form-actions'},build,button('refresh',renderPage),button('selectAllDeletable',()=>{for(const control of section.querySelectorAll('.pack-select:not(:disabled)')){control.checked=true;selected.add(control.value);}bulkHint.textContent=t('selectedItems')+': '+selected.size;}),button('deleteSelected',()=>{if(!selected.size){toast(t('selectAtLeastOne'));return;}return deleteStoredItems('/client-packs/delete',Array.from(selected));},'danger')),bulkHint);
 if(data.analysis?.excluded?.some(x=>x.client==='unknown'))body.append(node('div',{class:'info-box'},paragraph('clientPackUnknown'),node('ul',{},data.analysis.excluded.filter(x=>x.client==='unknown').map(x=>node('li',{text:x.filename}))),paragraph('clientSideUnknownHelp','hint')));
 if(data.mod_sides?.length){
  const choices=node('div',{class:'stack'},paragraph('clientSideHelp','hint'));
  for(const mod of data.mod_sides){
   const choice=select([['auto','clientSideAuto'],['required','clientSideRequired'],['optional','clientSideOptional'],['unsupported','clientSideServer']],mod.side);
   choice.setAttribute('aria-label',mod.filename);
   choice.disabled=mod.locked;
   const save=button('save',async()=>{save.disabled=true;try{await api('/client-packs/side',{sha256:mod.sha256,side:choice.value,basis:data.basis});toast(t('clientSideSaved'));await renderPage();}finally{save.disabled=false;}});
   save.disabled=mod.locked;
   choices.append(node('div',{class:'client-pack-version'},field(mod.filename,choice),mod.locked?paragraph('client_pack_server_only','hint'):save));
  }
  body.append(node('details',{},node('summary',{text:t('clientSideTitle')}),choices));
 }
 if(data.analysis?.issues?.length)body.append(node('div',{class:'info-box'},paragraph('client_pack_dependencies_blocked'),node('ul',{},data.analysis.issues.map(x=>node('li',{text:x.mod+' · '+(x.dependency||'')+' · '+errorText(x.reason)})))));
 if(!data.packs.length)body.append(paragraph('clientPackEmpty','hint'));else{const compare=button('compareClientPacks',openClientPackComparison);compare.disabled=data.packs.length<2;body.append(compare);}
 for(const pack of data.packs){
  const manifest=pack.manifest,card=node('div',{class:'client-pack-version'},node('div',{class:'list-row'},node('div',{},node('strong',{text:manifest.version}),node('small',{text:date(pack.created)+' · Minecraft '+manifest.runtime.version+' · '+manifest.runtime.loader+' '+manifest.runtime.loader_version+' · Java '+manifest.runtime.java})),pill(pack.current?'clientPackCurrent':pack.matches_current?'clientPackEquivalent':'clientPackOutdated',pack.current?'good':'warn')));
  const checkbox=input('checkbox');checkbox.className='pack-select';checkbox.value=pack.id;checkbox.setAttribute('aria-label',t('selectItem')+' '+manifest.version);checkbox.addEventListener('change',()=>{if(checkbox.checked)selected.add(pack.id);else selected.delete(pack.id);bulkHint.textContent=t('selectedItems')+': '+selected.size;});card.prepend(checkbox);const liveLinks=pack.matches_current!==false?(pack.active_links??data.links.filter(x=>x.pack_id===pack.id&&x.current!==false&&!x.revoked&&(x.expires==null||x.expires>Date.now()/1000)).length):0;card.append(node('p',{class:'hint',text:bytes(pack.size)+' · '+t('activeDownloadLinks')+': '+liveLinks}));
  const controls=node('div',{class:'form-actions'},node('a',{href:'/api/client-packs/'+pack.id+'/download',class:'text-button',text:t('clientPackDownload')}));
  if(pack.current)controls.append(button('clientPackShare',()=>{const days=select([['1','clientPackOneDay'],['7','clientPackSevenDays'],['14','clientPackFourteenDays'],['30','clientPackThirtyDays'],['unlimited','clientPackUnlimited']],'7'),result=node('div',{class:'stack'});modal('clientPackShare',node('div',{class:'stack'},paragraph('clientPackShareHint'),form([field('clientPackExpiry',days)],'clientPackCreateLink',async()=>{const value=await api('/client-packs/'+pack.id+'/share',{days:days.value==='unlimited'?null:Number(days.value)}),url=input('text',value.url,{readOnly:true,'aria-label':t('clientPackLink')});url.addEventListener('focus',()=>url.select());result.replaceChildren(field('clientPackLink',url),paragraph('clientPackLinkOnce','hint'),button('clientPackCopy',async()=>{await navigator.clipboard.writeText(value.url);toast(t('saved'));}));if(state.page==='mods')await renderPage();}),result));}));
  const remove=button('delete',()=>deleteStoredItems('/client-packs/delete',[pack.id]),'danger');controls.append(remove);card.append(controls);
  const details=node('details',{},node('summary',{text:t('clientPackContents')}),table(['name','version','status'],manifest.mods.map(x=>[x.mods.map(m=>m.name).join(', '),x.mods.map(m=>m.version).join(', '),t(x.client==='unknown'?'clientPackUnknownState':x.client==='unsupported'?'clientPackExcluded':x.client==='required'?'clientPackRequired':'clientPackRecommended')]),'noMods'));
  const changes=manifest.changes;details.append(node('p',{class:'hint',text:t('clientPackChanges')+': +'+changes.added.length+' / −'+changes.removed.length+' / Δ'+changes.changed.length}),node('ul',{},changes.added.map(x=>node('li',{text:'+ '+x})),changes.removed.map(x=>node('li',{text:'− '+x})),changes.changed.map(x=>node('li',{text:'Δ '+x}))));card.append(details);body.append(card);
 }
 if(data.links.length)body.append(node('details',{},node('summary',{text:t('clientPackLinks')}),table(['version','clientPackCreatedAt','clientPackExpiry','status','actions'],data.links.map(link=>[link.version||'—',date(link.created),link.expires==null?t('clientPackUnlimited'):date(link.expires),t(link.revoked?'clientPackRevoked':link.expires!=null&&link.expires<Date.now()/1000?'clientPackExpired':link.current===false?'clientPackOutdated':'clientPackActive'),!link.revoked?button('clientPackRevoke',()=>confirmAction('clientPackRevokeConfirm',async()=>{await api('/client-packs/links/'+link.id+'/revoke',{});await renderPage();}),'danger'):null]),'clientPackEmpty')));
 section.append(body);return section;
}

function prepareSettingsNavigation(holder,initialCategory=''){
 holder.append(node('section',{class:'setting-section'},node('h3',{text:t('setupWizard')}),paragraph('setupWizardIntro'),button('setupWizard',()=>setupWizard())));
 const keys=['runtimeSettings','serverProperties','worldManagement','minecraftPermissions','gameRules','smtp','providers','greetings','discord','schedules','users','infrastructure','applicationUpdate','changelog','setupWizard'];
 const names=['server','settings','worlds','players','settings','mail','mods','players','discord','uptime','players','settings','refresh','events','settings'],panels=Array.from(holder.children),jump=select([['','settingsAllSections'],...keys.map(key=>[key,key])],'');
 const summaries=node('div',{class:'settings-overview-panels'});
 function show(key){jump.value=key;holder.classList.toggle('is-filtered',!!key);summaries.hidden=!!key;for(const panel of panels)panel.hidden=!key||panel.dataset.settingsCategory!==key;$('modal').scrollTop=0;if(key==='gameRules'){const panel=panels.find(p=>p.dataset.settingsCategory===key);queueMicrotask(()=>attempt(panel.loadRules));}if(key==='infrastructure'){const panel=panels.find(p=>p.dataset.settingsCategory===key);queueMicrotask(()=>attempt(panel.loadInfrastructure));}}
 panels.forEach((panel,index)=>{decorateSettingsPanel(panel,keys[index],names[index]);const link=button(keys[index],()=>show(keys[index]),'settings-overview-link');link.prepend(icon(names[index]));link.append(node('small',{text:panel.querySelector(':scope > p')?.textContent||''}));summaries.append(link);});
 jump.addEventListener('change',()=>show(jump.value));
 holder.prepend(node('nav',{class:'settings-category-navigation','aria-label':t('settingsCategories')},field('settingsCategories',jump)),summaries);show(initialCategory);
}

function loaderLabel(runtime){const name={NEOFORGE:'NeoForge',FABRIC:'Fabric',FORGE:'Forge'}[runtime?.loader]||runtime?.loader||'—';return name+(runtime?.loader_version?' '+runtime.loader_version:'');}
function jobPayload(job,key){try{return JSON.parse(job[key]||'{}');}catch{return {};}}
function jobTitle(job){if(job.protection_update)return t('protectionUpdate');if(job.kind==='server_settings'&&job.combined_changes)return t('combinedChanges');if(job.kind==='server')return serverJobTitle(job.operation);if(['version_test','version_apply'].includes(job.kind)&&job.purpose!=='version')return t((job.purpose==='world'?'world':'settings')+(job.kind==='version_test'?'Test':'Apply'));return TEXT[state.language][job.kind]||t('maintenanceAction');}
function dependencyExplanation(issue){
 const key={version_predicate_unverified:'modDependencyUnverified',version_mismatch:'modDependencyMismatch',missing_dependency:'modDependencyMissing'}[issue.issue];
 if(!key)return [displayText(issue.filename||issue.id),errorText(issue.issue),displayText(issue.dependency)].filter(Boolean).join(' · ');
 const values={mod:displayText(issue.filename||issue.id),dependency:displayText(issue.dependency),required:displayText(issue.required),actual:displayText(issue.actual)};
 return t(key).replace(/\{(mod|dependency|required|actual)\}/g,(_,name)=>values[name]);
}
function jobRows(jobs,compact=false){
 const active=jobs.filter(x=>['planned','queued','running'].includes(x.state)),past=jobs.filter(x=>!active.includes(x)),holder=node('div',{class:'maintenance-jobs'+(compact?' is-compact':'')});
 if(!compact)holder.append(paragraph('maintenanceBackgroundHint','info-box'));
 function row(job){const result=jobPayload(job,'result'),payload=jobPayload(job,'payload'),stage=job.state==='running'?result.progress:null;
  const meta=node('div',{class:'job-meta'},node('small',{text:t('createdAt')+': '+date(job.created)}));
  const timing=node('div',{class:'job-timing'},node('strong',{text:jobTitle(job)}),meta);
  if(payload._scheduled_at)meta.append(node('small',{text:t('scheduledFor')+': '+date(payload._scheduled_at)+' · Europe/Berlin'}));
  if(result.started)meta.append(node('small',{text:t('duration')+': '+jobDuration(Math.max(0,(job.state==='running'?Date.now()/1000:job.updated)-result.started))}));
  const item=node('div',{class:'list-row maintenance-job'},timing,pill(stage?'progress_'+stage:'state_'+job.state,job.state==='failed'?'bad':job.state==='succeeded'?'good':''));
  const feedback=node('div',{class:'job-feedback'});
  const dependencyIssues=Array.isArray(result.dependency_report?.issues)?result.dependency_report.issues:[];
  if(dependencyIssues.length)feedback.append(node('p',{class:'job-error',text:t('modDependencyStopped')}),node('ul',{class:'validation-issues'},dependencyIssues.map(issue=>node('li',{text:dependencyExplanation(issue)}))),paragraph('modDependencyNextStep','hint'));
  else if(result.reason)feedback.append(node('p',{class:'job-error',text:errorText(result.reason)}),paragraph('jobFailureNextStep','hint'));
  if(feedback.childNodes.length)item.append(feedback);
  const evidence=node('details',{'data-job-key':job.id},node('summary',{text:t('details')}),node('p',{text:t('triggeredBy')+': '+(job.actor_name||t('system'))}),node('p',{text:t('requestedChange')+': '+planDetail(payload.configuration||payload.changes||payload)}));
  if(result.runtime)evidence.append(node('p',{text:t('verifiedActive')+': Minecraft '+result.runtime.version+' · '+loaderLabel(result.runtime)}));
  if(result.installed_mods?.length)evidence.append(node('ul',{},result.installed_mods.map(mod=>node('li',{text:mod.filename}))));
  if(result.phases?.length)evidence.append(node('ol',{},result.phases.map(phase=>node('li',{text:date(phase.at)+' · '+t('progress_'+phase.stage)}))));
  if(!compact)item.append(evidence);
  if(job.state==='queued'&&job.mode!=='manual')item.append(node('small',{text:t('waitingSafeMaintenance')}));
  const controls=node('div',{class:'form-actions'});if(state.user.admin&&job.state==='planned')controls.append(button('approveJob',async()=>{await api('/jobs/'+job.id+'/approve',{});await refresh();}));
  if(state.user.admin&&['planned','queued'].includes(job.state)){if(job.mode!=='immediate')controls.append(button('runJobNow',()=>runJobNow(job),'danger'));controls.append(button('cancelJob',async()=>{await api('/jobs/'+job.id+'/cancel',{});await refresh();}));}if(controls.childNodes.length)item.append(controls);return item;
 }
 async function refresh(){replaceJobRows(holder,await api(compact?'/jobs?summary=true':'/jobs'),compact);}
 if(active.length)holder.append(node('h4',{text:t('openJobs')+' · '+active.length}),...active.map(row));
 if(!jobs.length)holder.append(paragraph('noJobs'));
 if(past.length){if(compact)holder.append(...past.slice(0,3).map(row));else holder.append(node('details',{'data-job-key':'history'},node('summary',{text:t('jobHistory')+' · '+past.length}),past.map(row)));}
 return holder;
}
function runJobNow(job){modal('runJobNow',node('div',{class:'stack'},node('strong',{text:jobTitle(job)}),paragraph('runJobNowHint'),node('div',{class:'form-actions'},button('cancel',openMaintenance),button('runJobNow',async()=>{await api('/jobs/'+job.id+'/run-now',{confirmation:'run_now'});await openMaintenance();},'danger'))));}
function maintenancePanel(jobs){return node('section',{class:'card maintenance-card'},node('div',{class:'card-head'},node('h3',{text:t('maintenance')}),button('allMaintenanceJobs',openMaintenance)),node('div',{class:'card-body'},jobRows(jobs,true)));}
function replaceJobRows(target,jobs,compact=false){
 const opened=new Set(Array.from(target.querySelectorAll('details[open][data-job-key]'),e=>e.dataset.jobKey)),dialog=target.closest('dialog'),scroll=dialog?.scrollTop,next=jobRows(jobs,compact);
 for(const detail of next.querySelectorAll('details[data-job-key]'))detail.open=opened.has(detail.dataset.jobKey);
 const history=next.querySelector('details[data-job-key=history]');if(history&&Array.from(history.querySelectorAll('details[open]')).length)history.open=true;
 if(target.classList.contains('maintenance-jobs'))target.replaceWith(next);else target.replaceChildren(next);
 if(dialog)dialog.scrollTop=scroll;
}
function maintenanceRevision(jobs){return jobs.filter(x=>['planned','queued','running'].includes(x.state)).concat(jobs.filter(x=>!['planned','queued','running'].includes(x.state)).slice(0,3)).map(x=>JSON.stringify([x.id,x.state,x.updated])).join('|');}
async function openMaintenance(){const body=node('div',{class:'maintenance-full'});modal('maintenance',body);let busy=false,revision=null;async function refresh(){if(busy||!body.isConnected)return;busy=true;try{if(revision!==null){const summary=await api('/jobs?summary=true');updateGlobalJobs(summary);if(maintenanceRevision(summary)===revision)return;}const jobs=await api('/jobs');if(!body.isConnected)return;revision=maintenanceRevision(jobs);replaceJobRows(body,jobs);}finally{busy=false;}}await refresh();const timer=setInterval(()=>{if(!body.isConnected){clearInterval(timer);return;}attempt(refresh);},3000);}

// Only deliberate interaction refreshes the server-side idle deadline. No polling heartbeat.
let activitySentAt=0,activityPending=false;
async function reportSessionActivity(event){
 if(!event.isTrusted||document.hidden||document.body.dataset.authenticated!=='true'||activityPending||Date.now()-activitySentAt<60000)return;
 activityPending=true;activitySentAt=Date.now();
 try{await api('/auth/activity',{});}catch(error){if(error.code==='authentication_required'){closeModal();loginScreen();toast(t(error.code));}}finally{activityPending=false;}
}
for(const kind of ['pointerdown','keydown','scroll'])document.addEventListener(kind,reportSessionActivity,{passive:true,capture:true});

function decorateSettingsPanel(panel,key,symbol){panel.id='settings-category-'+key;panel.dataset.settingsCategory=key;panel.classList.add('settings-panel');const title=panel.querySelector('h3');if(title&&!title.querySelector('.ui-icon'))title.prepend(icon(symbol));const notes=Array.from(panel.querySelectorAll(':scope > p.hint,:scope > form > p.hint'));if(notes.length)panel.append(node('details',{class:'settings-help'},node('summary',{text:t('details')}),notes));}

function planDetail(value,depth=0){if(depth>4||value===null||value===undefined)return '';if(typeof value==='number')return Number.isFinite(value)?String(value):'';if(typeof value==='string')return ['null','undefined','[object Object]','NaN'].includes(value.trim())?'':value;if(Array.isArray(value))return value.map(x=>planDetail(x,depth+1)).filter(Boolean).join(', ');if(typeof value==='object')return Object.entries(value).map(([key,item])=>{const detail=planDetail(item,depth+1);return detail?key+': '+detail:'';}).filter(Boolean).join('; ');return '';}
function versionTarget(configuration){return t('targetRuntime')+': '+(configuration&&typeof configuration.version==='string'&&Number.isInteger(configuration.java)?'Minecraft '+configuration.version+' · Java '+configuration.java+' · '+loaderLabel(configuration):t('unknown'));}
function versionPlanResult(plan,hint='versionTestRequired'){
 if(!plan||!['passed','blocked'].includes(plan.metadata_checks))return paragraph('noCheckResult');
 const passed=plan.metadata_checks==='passed',children=[node('p',{class:'validation-status '+(passed?'validation-success':'validation-error'),text:t(passed?'metadataCheckPassed':'metadataCheckBlocked')}),node('p',{class:'validation-status validation-pending',text:t('isolatedTestPending')})];
 const issues=Array.isArray(plan.issues)?plan.issues.filter(x=>x&&typeof x==='object'):[];
 if(issues.length)children.push(node('ul',{class:'validation-issues'},issues.map(issue=>{const key=typeof issue.issue==='string'?issue.issue:'';const label=TEXT[state.language][key]?t(key):t('configurationIssue');const details=[planDetail(issue.dependency),planDetail(issue.required)].filter(Boolean);return node('li',{text:label+(details.length?' · '+details.join(' · '):'')});})));
 children.push(paragraph(hint,'hint'));
 if(passed&&typeof plan.id==='string'&&plan.id)children.push(button('testVersion',()=>maintenanceChoice('version_test',{id:plan.id},versionTarget(plan.configuration)),'primary'));
 return node('div',{class:'validation-result-body'},children);
}
async function requestVersionPlan(target,configuration,hint='versionTestRequired'){
 target.replaceChildren(paragraph('checkingConfiguration'));
 try{const plan=await api('/versions/plan',configuration);target.replaceChildren(versionPlanResult(plan,hint));}
 catch(error){if(error.code==='authentication_required')throw error;target.replaceChildren(node('p',{class:'validation-status validation-error',text:t('versionCheckUnavailable')}),node('p',{text:TEXT[state.language][error.code]?t(error.code):t('configurationIssue')}),paragraph('isolatedTestPending'));}
}

async function deleteStoredItems(endpoint,ids,done=renderPage){
 const preview=await api(endpoint,{ids});const content=node('div',{class:'stack'},paragraph('deleteStoredWarning'),node('p',{text:t('selectedItems')+': '+preview.count+' · '+t('spaceFreed')+': '+bytes(preview.bytes)}));
 if(preview.active_links)content.append(node('p',{class:'warning-box',text:t('linksWillRevoke')+': '+preview.active_links}));
 if(preview.versions?.length)content.append(node('ul',{},preview.versions.map(version=>node('li',{text:version}))));
 if(preview.current_packs)content.append(paragraph('deleteCurrentPackWarning','warning-box'));
 content.append(node('div',{class:'form-actions'},button('cancel',closeModal),button('deleteSelected',async()=>{await api(endpoint,{ids,confirmation:preview.confirmation});closeModal();toast(t('deletionComplete'));await done();},'danger')));modal('deleteSelected',content);
}

function curseForgeSearchPanel(installedMods){
 const section=node('section',{class:'card curseforge-search-panel'},node('div',{class:'card-head'},node('h3',{},icon('mods'),t('curseforgeSearchTitle')))),query=input('search',state.curseforgeQuery||'',{required:true,minLength:2,maxLength:120,placeholder:t('curseforgeSearchPlaceholder')}),results=node('div',{class:'curseforge-search-results','aria-live':'polite'});let requestGeneration=0;
 async function search(offset=0){const request=++requestGeneration,term=query.value.trim();state.curseforgeQuery=term;results.replaceChildren(paragraph('curseforgeSearching'));try{const data=await api('/mods/curseforge/search?'+new URLSearchParams({query:term,offset:String(offset)}));if(request!==requestGeneration)return;state.curseforgeSearchResult=data;draw(data);}catch(error){if(request!==requestGeneration)return;results.replaceChildren(node('p',{class:'warning-box',text:errorText(error.code)}));}}
 function draw(data){
  const heading=node('p',{class:'info-box',text:'Minecraft '+data.basis.version+' · '+loaderLabel(data.basis)+' · '+t('stableReleaseOnly')});results.replaceChildren(heading);
  if(!data.results.length)results.append(paragraph('curseforgeNoResults'));
  for(const item of data.results){
   const active=installedMods.some(row=>{let origin;try{origin=typeof row.origin==='string'?JSON.parse(row.origin):row.origin;}catch{return false;}return row.installed_enabled&&origin?.project_id===item.project_id&&origin?.file_id===item.file_id;});
   const action=button(active?'alreadyInstalled':'installSelectedMod',()=>maintenanceChoice('curseforge_install',{project_id:item.project_id,file_id:item.file_id,basis:data.basis},item.name+' · '+item.filename),'primary');action.disabled=active||!item.download_permitted;
   const card=node('article',{class:'curseforge-result'},node('div',{},node('h4',{},node('a',{href:item.url,target:'_blank',rel:'noopener noreferrer',text:item.name})),node('p',{text:item.summary}),node('small',{text:item.version+' · '+bytes(item.size)+(item.authors.length?' · '+item.authors.join(', '):'')})),action);
   if(item.required_projects.length)card.append(node('details',{},node('summary',{text:t('requiredDependencies')+': '+item.required_projects.length}),node('p',{text:t('curseforgeDependenciesHint')}),node('code',{text:item.required_projects.join(', ')})));
   if(!item.download_permitted)card.append(paragraph('curseforge_download_not_permitted','warning-box'));
   results.append(card);
  }
  if(data.next_offset!==null)results.append(button('nextSearchResults',()=>search(data.next_offset)));
 }
 section.append(node('div',{class:'card-body'},paragraph('curseforgeSearchIntro','hint'),form([field('curseforgeSearchLabel',query)],'searchCurseforge',()=>search(0)),results));if(state.curseforgeSearchResult)draw(state.curseforgeSearchResult);return section;
}

function sessionPolicyPanel(data){
 const hours=input('number',data.policy.absolute_seconds/3600,{min:1,max:168,step:1,required:true});
 const idle=input('number',data.policy.idle_seconds/60,{min:15,max:1440,step:1,required:true});
 const session=data.current_session;
 const panel=node('section',{class:'session-policy-panel stack'},node('h3',{text:t('sessionPolicy')}),paragraph('sessionPolicyIntro'),node('p',{text:t('sessionAbsoluteUntil')+': '+date(session.absolute_expires)}),node('p',{text:t('sessionIdleLimit')+': '+Math.round(session.idle_seconds/60)+' '+t('minutes')}));
 panel.append(form([node('div',{class:'setting-grid'},field('sessionHours',hours),field('sessionIdleMinutes',idle)),paragraph('sessionPolicyNextLogin','hint'),paragraph('rememberStandardPolicy','hint')],'save',async()=>{
  if(Number(idle.value)>Number(hours.value)*60){toast(t('idle_exceeds_session'));return;}
  await api('/auth/session-policy',{absolute_hours:Number(hours.value),idle_minutes:Number(idle.value)});toast(t('sessionPolicySaved'));
 }));return panel;
}

async function openVersionHistory(section){
 const original=Array.from(section.children).map(element=>({element,hidden:element.hidden}));for(const item of original)item.element.hidden=true;
 const body=node('div',{class:'version-history-view stack'}),search=input('search','',{maxLength:120,placeholder:t('versionHistorySearch')}),status=select([['','allStates'],...['metadata_passed','tested','applied','blocked','failed'].map(key=>[key,'state_'+key])],'');
 const records=node('div',{class:'version-history-records','aria-live':'polite','aria-busy':'false'}),pageHint=node('span',{class:'hint'});let cursors=[null],index=0,nextCursor=null,generation=0;
 const previous=node('button',{type:'button',text:t('previousPage'),onclick:()=>attempt(async()=>{if(!previous.disabled&&index>0){index--;await load(false);}})}),next=node('button',{type:'button',text:t('nextPage'),onclick:()=>attempt(async()=>{if(!next.disabled&&nextCursor){cursors[++index]=nextCursor;await load(false);}})});
 async function load(reset){if(reset){cursors=[null];index=0;}const request=++generation;previous.disabled=true;next.disabled=true;records.setAttribute('aria-busy','true');records.replaceChildren(paragraph('loading'));const query=new URLSearchParams({q:search.value.trim(),state:status.value,limit:'25'});if(cursors[index])query.set('cursor',cursors[index]);
  try{const data=await api('/versions/history?'+query);if(request!==generation||!body.isConnected)return;nextCursor=data.next_cursor;
   records.replaceChildren(...(data.records.length?data.records.map(plan=>{const details=node('details',{},node('summary',{text:t('details')}),node('p',{text:planDetail(plan.test_result||plan.report)||t('noCheckResult')}));const action=plan.actionable?button(plan.state==='tested'?'applyTestedVersion':'testVersion',()=>maintenanceChoice(plan.state==='tested'?'version_apply':'version_test',{id:plan.id},versionTarget(plan.configuration)),plan.state==='tested'?'primary':''):null;
    return node('article',{class:'version-history-record','data-history-id':plan.id},node('h4',{text:typeof plan.configuration?.version==='string'&&Number.isInteger(plan.configuration?.java)?'Minecraft '+plan.configuration.version+' · Java '+plan.configuration.java+' · '+loaderLabel(plan.configuration):t('unknown')}),node('p',{text:date(plan.created)}),pill('state_'+plan.state,plan.actionable&&plan.state==='tested'?'good':''),!plan.actionable&&['metadata_passed','tested'].includes(plan.state)?paragraph('historicalVersionPlan','hint'):null,action,details); }):[paragraph('noVersionHistory')]));pageHint.textContent=t('page')+' '+(index+1);
  }catch(error){if(error.code==='authentication_required')throw error;if(request!==generation)return;records.replaceChildren(errorParagraph(error.code));nextCursor=null;}
  finally{if(request===generation){records.setAttribute('aria-busy','false');previous.disabled=index===0;next.disabled=!nextCursor;}}
 }
 status.addEventListener('change',()=>attempt(()=>load(true)));
 body.append(node('div',{class:'form-actions'},button('backToVersions',()=>{generation++;body.remove();for(const item of original)item.element.hidden=item.hidden;$('modal').scrollTop=0;})),node('h3',{text:t('versionHistoryTitle')}),paragraph('versionHistoryIntro','hint'),form([node('div',{class:'setting-grid'},field('versionHistorySearch',search),field('status',status))],'searchVersionHistory',()=>load(true)),records,node('nav',{class:'form-actions', 'aria-label':t('versionHistoryTitle')},previous,pageHint,next));section.append(body);$('modal').scrollTop=0;await load(true);
}

let globalJobsBusy=false,globalJobsChecked=0;
function updateGlobalJobs(jobs){
 const bar=$('global-job-status');if(!bar)return;const active=jobs.filter(x=>['running','queued'].includes(x.state)),running=active.find(x=>x.state==='running');globalJobsChecked=Date.now();
 if(!state.user||!active.length){bar.hidden=true;bar.replaceChildren();return;}
 const current=running||active[0],result=jobPayload(current,'result'),phase=current.state==='running'&&result.progress?t('progress_'+result.progress):t('state_'+current.state);
 bar.replaceChildren(node('div',{},node('strong',{text:t('activeOperation')+': '+jobTitle(current)}),node('small',{text:phase+(active.length>1?' · '+t('queuedOperations')+': '+(active.length-(running?1:0)): '')})),button('maintenanceDetails',openMaintenance));bar.hidden=false;
}
async function refreshGlobalJobs(){
 if(globalJobsBusy||document.hidden||!state.user||document.body.dataset.authenticated!=='true'||Date.now()-globalJobsChecked<8000)return;
 globalJobsBusy=true;try{updateGlobalJobs(await api('/jobs?summary=true'));}catch(error){if(error.code==='authentication_required')throw error;const bar=$('global-job-status');if(bar&&!bar.hidden)bar.replaceChildren(paragraph('operationStatusUnavailable'),button('maintenanceDetails',openMaintenance));}finally{globalJobsBusy=false;}
}
setInterval(()=>{if(state.page!=='overview'||Date.now()-globalJobsChecked>20000)attempt(refreshGlobalJobs);},10000);

function draftControls(root){return Array.from(root.querySelectorAll('form input,form select,form textarea')).filter(e=>!e.disabled&&e.type!=='search'&&!e.closest('.version-history-view'));}
function draftValue(control){if(control.type==='password')return !!control.value;if(control.type==='file')return control.files.length;if(['checkbox','radio'].includes(control.type))return control.checked;return control.value;}
function clearSettingsDraft(){if(settingsDraftState){settingsDraftState.observer.disconnect();settingsDraftState.root.removeEventListener('input',settingsDraftState.touch,true);settingsDraftState.root.removeEventListener('change',settingsDraftState.touch,true);}settingsDraftState=null;}
function trackSettingsDraft(root){
 clearSettingsDraft();const baselines=new Map(),touched=new Set();function register(){for(const control of draftControls(root))if(!baselines.has(control))baselines.set(control,draftValue(control));}
 const touch=event=>{if(baselines.has(event.target))touched.add(event.target);};
 const observer=new MutationObserver(records=>{register();for(const record of records){const select=record.target instanceof Element?record.target.closest('select'):null;if(select&&baselines.has(select)&&!touched.size)baselines.set(select,draftValue(select));}});
 register();observer.observe(root,{childList:true,subtree:true});root.addEventListener('input',touch,true);root.addEventListener('change',touch,true);settingsDraftState={root,baselines,touched,observer};
}
function settingsDraftDirty(){if(!settingsDraftState)return false;for(const [control,before] of settingsDraftState.baselines)if(draftValue(control)!==before)return true;return false;}
function markSettingsFormSaved(form,detached=false){if(!settingsDraftState||(!detached&&!form.isConnected))return;for(const [control] of settingsDraftState.baselines)if(form.contains(control)){settingsDraftState.baselines.set(control,draftValue(control));settingsDraftState.touched.delete(control);}}
function dialogView(){return {nodes:Array.from($('modal-content').childNodes),title:$('modal-title').textContent,className:$('modal').className,scroll:$('modal').scrollTop};}
function restoreDialogView(view){$('modal-content').replaceChildren(...view.nodes);$('modal-title').textContent=view.title;$('modal').className=view.className;$('modal').scrollTop=view.scroll;}
function restoreSettingsReturn(){const view=settingsReturnView;settingsReturnView=null;if(view)restoreDialogView(view);}
function continueSettingsEditing(){const view=unsavedDialogView;unsavedDialogView=null;if(view)restoreDialogView(view);}
function requestUnsavedDecision(action){
 if(unsavedDialogView)return;unsavedDialogView=dialogView();$('modal').classList.remove('settings-dialog');$('modal-title').textContent=t('unsavedSettings');$('modal-content').replaceChildren(node('div',{class:'stack unsaved-settings-warning'},paragraph('unsavedSettingsHint'),node('div',{class:'form-actions'},button('continueEditing',continueSettingsEditing,'primary'),button('discardSettings',()=>{unsavedDialogView=null;settingsReturnView=null;clearSettingsDraft();action();},'danger'))));$('modal').scrollTop=0;
}
window.addEventListener('beforeunload',event=>{if(settingsDraftDirty()||pendingSettingsChanges){event.preventDefault();event.returnValue='';}});

async function openClientPackComparison(){
 const before=node('select',{'aria-label':t('beforePack'),required:true}),after=node('select',{'aria-label':t('afterPack'),required:true}),beforeDetails=node('p',{class:'hint pack-selection-meta'}),afterDetails=node('p',{class:'hint pack-selection-meta'}),result=node('div',{class:'client-pack-comparison-result','aria-live':'polite'}),available=new Map();let cursor=null,generation=0;
 const older=button('loadOlderPacks',()=>loadCatalog(false));
 async function loadCatalog(initial){const page=await api('/client-packs/catalog'+(!initial&&cursor?'?before='+cursor:''));const oldBefore=before.value,oldAfter=after.value;
  for(const pack of page.records){available.set(pack.id,pack);const label=pack.version;before.append(node('option',{value:pack.id,text:label}));after.append(node('option',{value:pack.id,text:label}));}
  cursor=page.next_cursor;older.hidden=!cursor;if(initial&&before.options.length>1){before.selectedIndex=1;after.selectedIndex=0;}else{before.value=oldBefore;after.value=oldAfter;}selectionDetails();if(initial)result.replaceChildren(paragraph('packComparisonReady','hint'));
 }
 function selectionDetails(){for(const [control,details] of [[before,beforeDetails],[after,afterDetails]]){const pack=available.get(control.value);details.textContent=pack?'Minecraft '+pack.runtime.version+' · '+loaderLabel(pack.runtime)+' · Java '+pack.runtime.java:'';}}
 for(const control of [before,after])control.addEventListener('change',()=>{generation++;selectionDetails();result.replaceChildren(paragraph('packComparisonReady','hint'));});
 async function compare(){const request=++generation;result.replaceChildren(paragraph('loading'));try{const data=await api('/client-packs/compare?'+new URLSearchParams({before:before.value,after:after.value}));if(request!==generation||!result.isConnected)return;
  const runtime=pack=>'Minecraft '+pack.runtime.version+' · '+loaderLabel(pack.runtime)+' · Java '+pack.runtime.java;
  const rows=data.changed.map(x=>[x.after.name,node('div',{},node('strong',{text:x.before.version}),node('small',{text:x.before.filename})),node('div',{},node('strong',{text:x.after.version}),node('small',{text:x.after.filename})),x.before.sha256!==x.after.sha256?t('packFileChanged'):t('packMetadataChanged')]);
  result.replaceChildren(node('h3',{text:data.before.version+' → '+data.after.version}),table(['comparisonPart','before','after'],[[t('runtimeSettings'),runtime(data.before),runtime(data.after)]],'noCheckResult'),node('p',{class:'info-box',text:t('packComparisonCounts')+': +'+data.added.length+' / −'+data.removed.length+' / Δ'+data.changed.length+' · '+t('packUnchanged')+': '+data.unchanged}),node('h4',{text:t('packAdded')}),node('ul',{},data.added.length?data.added.map(x=>node('li',{text:x.name+' · '+x.version})):node('li',{text:'—'})),node('h4',{text:t('packRemoved')}),node('ul',{},data.removed.length?data.removed.map(x=>node('li',{text:x.name+' · '+x.version})):node('li',{text:'—'})),node('h4',{text:t('packChanged')}),table(['name','before','after','details'],rows,'packNoChangedMods'));
 }catch(error){if(error.code==='authentication_required')throw error;if(request===generation)result.replaceChildren(errorParagraph(error.code));}}
 const body=node('div',{class:'stack client-pack-comparison'},paragraph('compareClientPacksHint','hint'),form([node('div',{class:'setting-grid'},node('div',{},field('beforePack',before),beforeDetails),node('div',{},field('afterPack',after),afterDetails)),older],'compareClientPacks',compare),result);modal('compareClientPacks',body);await loadCatalog(true);
}

function updateChangeBasket(data=null){
 if(data)pendingModChanges=data.mods.filter(x=>!x.protected&&(x.remove_pending!=null||!x.metadata.client_installer&&((x.state==='staged'&&x.enabled)||(x.state==='installed'&&!!x.enabled!==!!x.installed_enabled))));
 const bar=$('collected-changes');if(!bar)return;const count=pendingSettingsChanges?Object.keys(pendingSettingsChanges.changes.properties).length+(pendingSettingsChanges.changes.memory_mb!==undefined||pendingSettingsChanges.changes.container_memory_mb!==undefined?1:0):0;bar.hidden=!count&&!pendingModChanges.length;
 if(!bar.hidden)bar.replaceChildren(...[node('strong',{text:t('collectedChanges')}),node('span',{text:t('serverProperties')+': '+count+' · '+t('mods')+': '+pendingModChanges.length}),button('reviewCollectedChanges',openCollectedChanges,'primary'),pendingSettingsChanges?button('discardCollectedSettings',()=>confirmAction('discardCollectedSettingsHint',()=>{pendingSettingsChanges=null;updateChangeBasket();})):null].filter(child=>child!==null&&child!==undefined));
}
async function refreshChangeBasket(){if(state.user?.admin)updateChangeBasket(await api('/mods'));}
async function openCollectedChanges(){
 const data=await api('/mods');updateChangeBasket(data);if(!pendingSettingsChanges){maintenanceChoice('apply_mods',{},pendingModChanges.map(x=>x.filename+' → '+t(x.remove_pending!=null?'uninstallMod':x.enabled?'enabled':'disabled')).join('; '));return;}
 const payload={...pendingSettingsChanges,_collected_settings:true};if(pendingModChanges.length){payload.include_pending_mods=true;payload.mod_fingerprint=data.fingerprint;}maintenanceChoice('server_settings',payload,pendingModChanges.length?pendingModChanges.map(x=>x.filename+' → '+t(x.remove_pending!=null?'uninstallMod':x.enabled?'enabled':'disabled')).join('; '):null);
}

async function rememberedSessionsPanel(){
 const panel=node('section',{class:'stack remembered-sessions'},node('h3',{text:t('mySessions')}),paragraph('mySessionsHint','hint'));
 const draw=async()=>{const rows=await api('/auth/sessions');const records=node('div',{class:'stack'},rows.map(row=>node('div',{class:'list-row'},node('div',{},node('strong',{text:t(row.current?'thisSession':'otherSession')}),node('small',{text:t('sessionCreated')+': '+date(row.created)}),node('small',{text:t('sessionAbsoluteUntil')+': '+date(row.expires)})),pill(row.remember_days?'rememberedSession':'standardSession'),row.current?null:button('revokeSession',async()=>{await api('/auth/sessions/revoke',{identifier:row.id});await draw();},'danger'))));panel.querySelector('.session-records')?.remove();records.classList.add('session-records');panel.append(records);};
 panel.append(button('revokeOtherSessions',async()=>{await api('/auth/sessions/revoke',{identifier:'others'});await draw();},'danger'));await draw();return panel;
}

function deliveryHistory(records){
 let page=0;const content=node('div'),range=node('span',{class:'hint','aria-live':'polite'}),previous=button('previousPage',()=>{page--;draw();}),next=button('nextPage',()=>{page++;draw();});
 function draw(){page=Math.max(0,Math.min(page,Math.ceil(records.length/10)-1));const offset=page*10;content.replaceChildren(table(['createdAt','status'],records.slice(offset,offset+10).map(x=>[date(x.created),pill('notification_'+x.state)]),'noNotifications'));range.textContent=(records.length?offset+1:0)+'–'+Math.min(offset+10,records.length)+' / '+records.length;previous.disabled=page===0;next.disabled=offset+10>=records.length;}
 draw();return node('section',{class:'delivery-history stack'},paragraph('deliveryHistoryLimit','hint'),content,node('nav',{class:'form-actions','aria-label':t('notificationHistory')},previous,range,next));
}
async function manageEventHistory(category=''){
 const data=await api('/events/cleanup-policy'),cfg=data.policy;
 const enabled=input('checkbox');enabled.checked=cfg.enabled;
 const days=input('number',cfg.retention_days,{min:1,max:3650,step:1,required:true}),deliveryDays=input('number',cfg.delivery_days,{min:1,max:3650,step:1,required:true}),interval=input('number',cfg.interval_hours,{min:1,max:168,step:1,required:true});
 const before=input('datetime-local',new Date(Date.now()-30*86400000-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16),{required:true});
 const scope=select([['','allEvents'],['auth','auth'],['player','players'],['server','server'],['mods','mods'],['backup','backup'],['maintenance','maintenance'],['email','smtp'],['discord','discord'],['audit','audit'],['system','system']],category);
 const result=node('p',{'aria-live':'polite'});
 const automatic=form([node('label',{class:'checkbox-field'},enabled,t('automaticHistoryCleanup')),node('div',{class:'setting-grid'},field('eventRetentionDays',days),field('deliveryRetentionDays',deliveryDays),field('cleanupIntervalHours',interval)),paragraph('historyCleanupHint','hint')],'save',async()=>{await api('/events/cleanup-policy',{enabled:enabled.checked,retention_days:Number(days.value),delivery_days:Number(deliveryDays.value),interval_hours:Number(interval.value)});toast(t('saved'));});
 const body=node('div',{class:'history-settings stack'},node('h3',{text:t('automaticHistoryCleanup')}),automatic,node('h3',{text:t('deleteOldEvents')}),paragraph('manualHistoryCleanupHint','hint'),form([node('div',{class:'setting-grid'},field('eventsBefore',before),field('category',scope))],'previewCleanup',async()=>{
  const preview=await api('/events/cleanup-preview',{before:Date.parse(before.value)/1000,category:scope.value});
  const confirmation=node('section',{class:'history-cleanup-confirm stack'},node('p',{text:t('cleanupAffected')+': '+preview.count}),node('p',{text:t('eventsBefore')+': '+date(preview.before)}),paragraph('cleanupPermanent','hint'));
  const confirm=button('deleteOldEvents',async()=>{const deleted=await api('/events/cleanup',{token:preview.token});result.textContent=t('eventsDeletedCount')+': '+deleted.deleted;confirmation.remove();if(state.page==='events'&&pageLiveRefresh)await pageLiveRefresh();},'danger');confirm.disabled=!preview.count;
  confirmation.append(node('div',{class:'form-actions'},button('cancel',()=>confirmation.remove()),confirm));body.querySelector('.history-cleanup-confirm')?.remove();body.append(confirmation);
 }),result);
 if(data.last)body.append(node('p',{class:'hint',text:t('lastHistoryCleanup')+': '+date(data.last.at)}));modal('manageHistory',body);
}

function gameRulesSettings(){
 const content=node('div',{class:'stack'}),world=node('p',{class:'game-rules-world'}),section=node('section',{class:'setting-section game-rules-panel'},node('h3',{text:t('gameRules')}),paragraph('gameRulesIntro'),world,content);
 let busy=false,loaded=false;
 section.loadRules=async(force=false)=>{
  if(busy||loaded&&!force||!section.isConnected)return;busy=true;
  try{const data=await api('/server/game-rules');if(!section.isConnected)return;loaded=true;world.textContent=t('activeWorld')+': '+data.world+' · Minecraft '+data.version;
   content.replaceChildren(...data.rules.map(rule=>{const enabled=input('checkbox');enabled.checked=rule.enabled===true;enabled.disabled=!rule.supported;const status=node('span',{class:'pill',text:t(rule.supported?(rule.enabled?'enabled':'disabled'):'unsupported_game_rule')});
    const entry=form([node('label',{class:'checkbox-field'},enabled,t('gameRule_'+rule.key)),node('p',{class:'hint',text:t('gameRuleHint_'+rule.key)}),status],'applyGameRule',async()=>{
     const result=await api('/server/game-rules',{key:rule.key,enabled:enabled.checked,expected:rule.enabled,basis:data.basis});rule.enabled=result.enabled;status.textContent=t(result.enabled?'enabled':'disabled');markSettingsFormSaved(entry);toast(t('gameRuleSaved'));
    });entry.classList.add('game-rule');entry.querySelector('button[type=submit]').disabled=!rule.supported;return entry;}));
  }catch(error){loaded=false;content.replaceChildren(errorParagraph(error.code||'game_rules_server_offline'));}
  finally{busy=false;}
 };
 section.append(button('refreshGameRules',()=>{if(settingsDraftDirty()){requestUnsavedDecision(()=>section.loadRules(true));return;}return section.loadRules(true);}));return section;
}

function hasVersionProvider(mod){try{const origin=typeof mod.origin==='string'?JSON.parse(mod.origin):mod.origin;return ['curseforge','modrinth','manual_patch'].includes(origin?.provider)&&!!origin.url;}catch{return false;}}
async function chooseModVersion(mod){
 const versions=select([['','selectModVersion']],'');versions.required=true;const keep=input('checkbox');keep.checked=true;
 const description=node('p',{class:'hint'}),records=new Map();let next=0,basis=null,loading=false;
 const older=button('loadOlderModVersions',()=>load(false));
 function details(){const value=records.get(versions.value);description.textContent=value?value.filename+' · '+(value.published?date(Date.parse(value.published)/1000):'—'):t('modVersionChooseHint');}
 async function load(first){if(loading)return;loading=true;older.disabled=true;try{const data=await api('/mods/'+mod.id+'/versions?offset='+(first?0:next));basis=data.basis;next=data.next_offset;
  for(const version of data.versions){if(records.has(version.id))continue;records.set(version.id,version);versions.append(node('option',{value:version.id,text:version.name+' · '+version.filename}));}
  older.hidden=next===null;details();if(!records.size)description.textContent=t('no_stable_compatible_version');
 }finally{loading=false;older.disabled=false;}}
 versions.addEventListener('change',details);
 const body=node('div',{class:'mod-version-picker stack'},node('strong',{text:mod.metadata.mods.map(x=>x.name).join(', ')}),node('p',{text:t('installedFile')+': '+mod.filename}),paragraph('modVersionChooseHint','hint'),mod.locally_patched?paragraph('modVersionLocalPatchHint','warning-box'):null,
  form([field('selectModVersion',versions),description,older,node('label',{class:'checkbox-field'},keep,t('pinModVersion')),paragraph('pinModVersionHint','hint')],'stageSelectedVersion',async()=>{if(!basis||!records.has(versions.value))return;await api('/jobs',{kind:'mod_version',mode:'manual',approved:true,payload:{id:mod.id,version:versions.value,basis,pin:keep.checked}});closeModal();toast(t('modVersionDownloadQueued'));if(state.page==='mods')await renderPage();}));
 modal('chooseModVersion',body);await load(true);
}


function infrastructureSettings(cfg){
 const content=node('div',{class:'infrastructure-controls stack'}),section=node('section',{class:'setting-section infrastructure-panel'},node('h3',{text:t('infrastructure')}),paragraph('infrastructureControlsIntro'),content);
 let loaded=false,busy=false;
 section.loadInfrastructure=async(force=false)=>{
  if(busy||loaded&&!force||!section.isConnected)return;busy=true;
  try{
   const [web,game,tls,connections]=await Promise.all([api('/infrastructure/web'),api('/infrastructure/game'),api('/infrastructure/tls'),api('/infrastructure/connections')]);if(!section.isConnected)return;loaded=true;
   const tlsPanel=node('div',{class:'stack'},node('h4',{text:t('localHttps')}),paragraph(tls.managed?'localHttpsHint':'proxyHttpsHint'));
   if(tls.managed)tlsPanel.append(node('p',{text:t('validUntil')+': '+date(tls.expires)}),node('p',{class:'fingerprint',text:'SHA-256: '+tls.authority_fingerprint}),node('div',{class:'form-actions'},node('a',{href:'/api/infrastructure/tls/authority',class:'text-button',text:t('downloadLocalAuthority')}),button('renewLocalCertificate',async()=>{if(!confirm(t('renewLocalCertificateConfirm')))return;await api('/infrastructure/tls/renew',{confirmed:true});toast(t('localCertificateRenewed'));await section.loadInfrastructure(true);})));
   const proxies=input('text',connections.proxies,{maxLength:500}),networks=input('text',connections.networks,{maxLength:500}),networkConfirm=input('checkbox');networkConfirm.required=true;
   const connectionForm=form([node('h4',{text:t('connectionPolicy')}),paragraph('connectionPolicyHint'),node('p',{text:t('connectionPeer')+': '+connections.peer}),field('trustedProxyAddresses',proxies),field('localNetworkRanges',networks),node('label',{class:'checkbox-field'},networkConfirm,t('confirmConnectionPolicy'))],'save',async()=>{await api('/infrastructure/connections',{proxies:proxies.value,networks:networks.value,confirmed:networkConfirm.checked});markSettingsFormSaved(connectionForm);toast(t('saved'));await section.loadInfrastructure(true);});connectionForm.querySelector('button[type=submit]').disabled=!connections.local_connection;
   const target=input('url',web.address,{required:true,maxLength:300}),confirmation=input('text','',{maxLength:300,autocomplete:'off'});
   const webAddress=form([node('h4',{text:t('infraWebAddress')}),node('p',{text:t('currentWebAddress')+': '+web.address}),paragraph('webAddressPrepareHint'),field('newWebAddress',target),field('webAddressConfirmation',confirmation)],'prepareWebAddress',async()=>{
    const saved=await api('/infrastructure/web',{address:target.value,external_web:web.external_web,basis:web.basis,confirmation:confirmation.value});markSettingsFormSaved(webAddress);toast(t('saved'));await section.loadInfrastructure(true);if(saved.pending)content.querySelector('.info-box')?.scrollIntoView({block:'center'});
   });
   if(web.pending){const pending=node('div',{class:'info-box stack'},node('strong',{text:t('pendingWebAddress')}),node('p',{text:web.pending.address+' · '+t('validUntil')+': '+date(web.pending.expires)}));
    if(location.origin===web.pending.address)pending.append(button('activateWebAddress',async()=>{await api('/infrastructure/web/activate',{basis:web.basis});toast(t('webAddressActivated'));await section.loadInfrastructure(true);},'primary'));
    else pending.append(node('a',{href:web.pending.address,target:'_blank',rel:'noopener noreferrer',class:'text-button',text:t('openNewWebAddress')}));webAddress.prepend(pending);
   }
   const external=input('checkbox');external.checked=web.external_web;external.disabled=!web.local_connection||!(web.proxy_configured||web.local_network_configured);
   const webConfirm=input('checkbox');webConfirm.required=true;
   const webForm=form([node('h4',{text:t('infraPublicApproval')}),node('label',{class:'checkbox-field'},external,t('allowExternalWeb')),paragraph('externalWebHint'),!web.local_connection?paragraph('web_access_requires_local_connection','hint'):!web.proxy_configured&&!web.local_network_configured?paragraph('web_proxy_setup_required','hint'):null,node('label',{class:'checkbox-field'},webConfirm,t('confirmAccessChange'))],'save',async()=>{
    await api('/infrastructure/web',{address:web.address,external_web:external.checked,basis:web.basis});markSettingsFormSaved(webForm);toast(t('saved'));await section.loadInfrastructure(true);
   });webForm.querySelector('button[type=submit]').disabled=external.disabled;
   const publicGame=input('checkbox');publicGame.checked=game.public_game===true;publicGame.disabled=!game.ready;
   const gameConfirm=input('checkbox');gameConfirm.required=true;
   const gameForm=form([node('h4',{text:t('infraGameAccess')}),node('label',{class:'checkbox-field'},publicGame,t('allowPublicGame')),paragraph('publicGameHint'),!game.ready?paragraph(game.public_game===null?'game_access_unavailable':'game_access_guard_update_required','hint'):null,node('label',{class:'checkbox-field'},gameConfirm,t('confirmGameAccessChange'))],'save',async()=>{
    await api('/infrastructure/game',{public_game:publicGame.checked,basis:game.basis,confirmed:gameConfirm.checked});markSettingsFormSaved(gameForm);toast(t('saved'));await section.loadInfrastructure(true);
   });gameForm.querySelector('button[type=submit]').disabled=!game.ready;
   content.replaceChildren(...[tlsPanel,webAddress,webForm,gameForm,connectionForm,game.update_available?node('div',{class:'info-box stack'},paragraph('protectionUpdateHint'),button('queueProtectionUpdate',async()=>{await api('/infrastructure/game/update',{basis:game.update_basis});toast(t('jobQueued'));await refreshGlobalJobs();})):null,node('div',{class:'form-actions'},button('refresh',()=>section.loadInfrastructure(true)),node('a',{href:'/api/diagnostics',class:'text-button',text:t('diagnostics')}))].filter(Boolean));
  }catch(error){if(!loaded)content.replaceChildren(errorParagraph(error.code));throw error;}finally{busy=false;}
 };
 return section;
}


function applicationUpdateSettings(value={}){
 const phase=['checking','backup','updating','health','complete','failed','rolled_back'].includes(value.phase)?value.phase:'ready';
 return node('section',{class:'setting-section application-update-panel'},node('h3',{},icon('refresh'),t('applicationUpdate')),paragraph('applicationUpdateIntro'),
  value.version?node('p',{text:t('installedVersion')+': '+value.version}):null,
  paragraph('applicationUpdatePhase_'+phase,phase==='failed'||phase==='rolled_back'?'warning-box':'info-box'),
  node('ol',{class:'setup-guide'},['applicationUpdateStep1','applicationUpdateStep2','applicationUpdateStep3'].map(key=>node('li',{text:t(key)}))),
  paragraph('applicationUpdateKeepFolder','hint'),node('a',{href:'/api/application-update/template',class:'text-button',text:t('applicationUpdateDownload')}));
}

const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../mcj/static/app.js'),'utf8');
const page=source.slice(source.indexOf('async function backupsPage(){'),source.indexOf('async function eventsPage('));

test('bulk selection excludes protected backups and drops selections that become unavailable',async()=>{
 const buttons=new Map(),submitted=[],messages=[];
 let records=[{id:'a',created:1,size:10,archive_available:true,protected:false},
              {id:'b',created:2,size:10,archive_available:true,protected:true},
              {id:'c',created:3,size:10,archive_available:false,protected:false},
              {id:'d',created:4,size:10,archive_available:true,protected:false}];
 const element=()=>({value:'',isConnected:true,replaceChildren(){},prepend(){},setAttribute(){},addEventListener(){},contains(){return false;},querySelectorAll(){return[];}});
 const content=element(),context={state:{user:{admin:true}},document:{activeElement:null},URLSearchParams,Set,
  select:()=>element(),input:()=>element(),node:()=>element(),button:(label,action)=>{const e=element();if(!buttons.has(label))buttons.set(label,action);return e;},
  $:()=>content,heading:()=>element(),field:()=>element(),paragraph:()=>element(),table:()=>element(),pill:()=>element(),
  t:x=>x,date:String,bytes:String,backupProtectionPanel:()=>({element:element(),refresh:async()=>{}}),
  api:async()=>({records:records.map(x=>({...x})),next_cursor:''}),toast:x=>messages.push(x),
  deleteStoredItems:async(endpoint,ids)=>submitted.push({endpoint,ids:[...ids]}),attempt:f=>f()};
 vm.createContext(context);vm.runInContext(page+'\nthis.openBackups=backupsPage;',context);
 await context.openBackups();buttons.get('selectAllDeletable')();await buttons.get('deleteSelected')();
 assert.deepEqual(submitted.map(x=>x.ids),[['a','d']]);
 records=[{...records[0],protected:true},records[1],records[2],{...records[3],archive_available:false},
          {id:'e',created:5,size:10,archive_available:true,protected:false}];
 await context.pageLiveRefresh();await buttons.get('deleteSelected')();
 assert.equal(submitted.length,1);assert.equal(messages.at(-1),'selectAtLeastOne');
 buttons.get('selectAllDeletable')();await buttons.get('deleteSelected')();
 assert.deepEqual(submitted[1],{endpoint:'/backups/delete',ids:['e']});
 records=Array.from({length:125},(_,n)=>({id:'backup-'+n,created:n,size:10,archive_available:true,protected:false}));
 await context.pageLiveRefresh();buttons.get('selectAllDeletable')();await buttons.get('deleteSelected')();
 assert.equal(submitted[2].ids.length,100);assert.equal(messages.at(-1),'backupSelectionLimit');
});

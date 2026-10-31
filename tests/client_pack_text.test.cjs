const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../mcj/static/client-pack.js'),'utf8');
test('missing mod names and versions never appear as raw null or undefined',()=>{
 for(const language of ['de','en']){
  const c={};vm.createContext(c);vm.runInContext(source.slice(source.indexOf('const words='),source.indexOf('const byId='))+`\nlet language='${language}';const text=key=>words[language][key];`+source.match(/^function readableValue.*$/m)[0]+'\nthis.read=readableValue;this.words=words;',c);
  for(const value of [null,undefined,{},NaN,Infinity,'','null','undefined','None','[object Object]']){
   assert.equal(c.read(value,'versionUnknown'),c.words[language].versionUnknown);
   assert.equal(c.read(value,'unknownMod'),c.words[language].unknownMod);
  }
  assert.equal(c.read('6.0.11-adapted-1.31','versionUnknown'),'6.0.11-adapted-1.31');
  assert.equal(c.read(25,'versionUnknown'),'25');
 }
 assert(source.includes("name.textContent=readableValue(mod.name,'unknownMod')"));
 assert(source.includes("version.textContent=readableValue(mod.version,'versionUnknown')"));
});

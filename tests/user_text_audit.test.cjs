const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..'),staticRoot=path.join(root,'mcj/static');
function main(){const c={};vm.createContext(c);for(const f of ['i18n.js','setup-wizard.js','server-property-help.js'])vm.runInContext(fs.readFileSync(path.join(staticRoot,f),'utf8'),c);vm.runInContext('this.words=TEXT;this.propertyWords=SERVER_PROPERTY_HELP;',c);return c;}
function bootstrap(){const s=fs.readFileSync(path.join(staticRoot,'bootstrap-i18n.js'),'utf8'),c={};vm.createContext(c);vm.runInContext(s.slice(s.indexOf(' const de='),s.indexOf(" let language='de'"))+'\nthis.words={de,en}',c);return c.words;}
function client(){const s=fs.readFileSync(path.join(staticRoot,'client-pack.js'),'utf8'),c={};vm.createContext(c);vm.runInContext(s.slice(s.indexOf('const words='),s.indexOf('const byId='))+'\nthis.words=words',c);return c.words;}
function placeholders(value){return [...String(value).matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)].map(m=>m[1]).sort();}
const loaded=main(),catalogues={manager:loaded.words,bootstrap:bootstrap(),client:client()};
test('every DE/EN catalogue has parallel non-empty keys, placeholders and no broken encoding',()=>{
 for(const [name,words]of Object.entries(catalogues)){
  assert.deepEqual(Object.keys(words.de).sort(),Object.keys(words.en).sort(),name);
  for(const key of Object.keys(words.de)){
   for(const lang of ['de','en']){
    const values=Array.isArray(words[lang][key])?words[lang][key]:[words[lang][key]];
    assert(values.length,name+'/'+key);
    for(const v of values){assert.equal(typeof v,'string');assert(v.trim(),name+'/'+lang+'/'+key);assert(!/[\uFFFD]|Ã[\x80-\xBF]|Â[\x80-\xBF]/.test(v));assert(!/^(?:null|undefined|NaN|\[object Object\])$/.test(v));}
   }
   assert.deepEqual(placeholders(words.de[key]),placeholders(words.en[key]),name+'/'+key);
  }
 }
 for(const [key,pair]of Object.entries(loaded.propertyWords)){assert.equal(pair.length,2,key);assert(pair.every(v=>typeof v==='string'&&v.trim()));}
});
test('HTML and JavaScript beginner labels are present in both languages',()=>{
 for(const [file,words,attribute]of [['index.html',loaded.words,'data-i18n'],['bootstrap.html',catalogues.bootstrap,'data-setup-i18n'],['bootstrap-expired.html',catalogues.bootstrap,'data-setup-i18n']]){
  const source=fs.readFileSync(path.join(staticRoot,file),'utf8');
  for(const m of source.matchAll(new RegExp(attribute+'="([^"]+)"','g')))for(const lang of ['de','en'])assert(words[lang][m[1]],file+'/'+lang+'/'+m[1]);
 }
 const script=fs.readFileSync(path.join(staticRoot,'bootstrap.js'),'utf8');
 for(const m of script.matchAll(/SetupI18n\.text\(['"]([^'"]+)['"]/g))for(const lang of ['de','en'])assert(catalogues.bootstrap[lang][m[1]],m[1]);
});
test('English paths do not reuse German explanatory sentences',()=>{
 for(const [name,words]of Object.entries(catalogues))for(const key of Object.keys(words.de)){
  const en=String(words.en[key]);
  if(en.split(/\s+/).length>=6)assert.notEqual(en,String(words.de[key]),name+'/'+key);
  assert(!/\b(?:Bitte|Wähle|gespeichert|fehlgeschlagen|Wiederherstellungscodes|Einrichtungszugang)\b/.test(en),name+'/'+key);
 }
});
test('first-start wording names both methods and distinguishes SMTP acceptance from receipt',()=>{
 assert.match(catalogues.bootstrap.en.accountHelp,/email codes or an authenticator/);
 assert.match(catalogues.bootstrap.de.accountHelp,/E-Mail oder eine Authenticator/);
 for(const lang of ['de','en']){
  const help=loaded.words[lang].emailSetupCodeHelp;
  assert.match(help,/10/);assert.match(help,lang==='de'?/Postfach/:/inbox/);
  assert.match(loaded.words[lang].emailSetupTransportHelp,/STARTTLS/);
 }
});
if(require.main===module&&process.argv.includes('--inventory')){
 process.stdout.write(JSON.stringify({catalogues:Object.fromEntries(Object.entries(catalogues).map(([name,v])=>[name,{de_keys:Object.keys(v.de).length,en_keys:Object.keys(v.en).length}])),server_property_help_pairs:Object.keys(loaded.propertyWords).length})+'\n');
}

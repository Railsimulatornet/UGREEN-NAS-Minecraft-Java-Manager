"""Immutable client exports. Only public mod metadata and reviewed redistributable files.

Provider credentials stay with the provider adapter. Share capabilities are hashed;
their plaintext belongs in a browser fragment and POST body, never a URL/log.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlparse
import zipfile
import httpx
from . import mods, sources, __version__
from .project_paths import project_path
from .maven_ranges import matches as maven_matches
from .version_ranges import matches as fabric_matches

RUNTIME_KEYS=('version','java','loader','loader_version')
CARRY_HASH='0b03470f4d923aa8a5919cb0f4dcd2744d1239cfc91a7611f744ef5e87b79bea'
# Exact artifact, Minecraft and loader versions observed in real Prism clients.
CARRY_REVIEWED_LOADERS={'26.3.0.97','26.3.0.99'}
EXPORT_POLICY='reviewed-client-export-6'
CREATE_ASSET_HASH='ef87fe5709f1ba1f5b8bb20a2925b5afb4669e178fd6d8bf10c167759eefe37a'
CREATE_ORIGINAL_HASH='4e8684618edeedae5dbfbe5ec8ba05d57c8c251cb34beb69160f53cbd97b4099'
CREATE_IRIS_HASH='9008cd82a9233fdb0ddadb33cd5fb11c9fc26b9ea102ad245319a9aa1b2964c8'
CF_BOTH={1651484:('create','https://www.curseforge.com/minecraft/mc-mods/create-adapted'),
         1683430:('createaddition','https://www.curseforge.com/minecraft/mc-mods/create-crafts-additions-adapted'),
         227874:('dynamiclights','https://www.curseforge.com/minecraft/mc-mods/dynamic-lights'),
         1680731:('immersive_aircraft','https://www.curseforge.com/minecraft/mc-mods/immersive-aircraft-unofficial-port'),
         422301:('sophisticatedbackpacks','https://www.curseforge.com/minecraft/mc-mods/sophisticated-backpacks'),
         618298:('sophisticatedcore','https://www.curseforge.com/minecraft/mc-mods/sophisticated-core')}
HEX64=re.compile('[0-9a-f]{64}')
TOKEN=re.compile('[A-Za-z0-9_-]{43}')

def runtime(value):
    result={k:value.get(k) for k in RUNTIME_KEYS}
    if not isinstance(result['version'],str) or not re.fullmatch(r'[A-Za-z0-9.+_-]{1,80}',result['version']) or type(result['java']) is not int or result['java'] not in [17,21,25] or result['loader'] not in ['FABRIC','FORGE','NEOFORGE'] or not isinstance(result['loader_version'],str) or not re.fullmatch(r'[A-Za-z0-9.+_-]{1,100}',result['loader_version']):
        raise ValueError('client_pack_runtime_unverified')
    return result

def read_bounded(path,limit):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not 0<before.st_size<=limit:raise ValueError('client_pack_file_limit')
        raw=stream.read(limit+1);after=os.fstat(stream.fileno())
    if len(raw)>limit or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('client_pack_source_changed')
    return raw

def hashes(raw):return {name:getattr(hashlib,name)(raw).hexdigest() for name in ['sha1','sha256','sha512']}

def snapshot(root,st):
    """Controller only: observe installed JARs, not desired/staged DB rows."""
    active=runtime(json.loads(read_bounded(project_path(root,'control/runtime/runtime.json'),65536)))
    with st.db() as db:rows={x['sha256']:dict(x) for x in db.execute('SELECT sha256,source,origin FROM mods WHERE installed_enabled=1')}
    folder=project_path(root,'server/mods');paths=sorted(folder.glob('*.jar'))
    if len(paths)>512:raise ValueError('client_pack_mod_limit')
    records=[];total=0
    for path in paths:
        if not re.fullmatch(r'[A-Za-z0-9_.+() -]{1,160}\.jar',path.name):raise ValueError('client_pack_filename_invalid')
        raw=read_bounded(path,mods.MAX_JAR);total+=len(raw)
        if total>512*1024*1024:raise ValueError('client_pack_mod_limit')
        digest=hashes(raw);row=rows.get(digest['sha256'],{});origin=json.loads(row.get('origin') or '{}')
        records.append({'filename':path.name,'hashes':digest,'size':len(raw),'metadata':mods.inspect_jar(raw),
                        'source':row.get('source','unmanaged'),'origin':{k:origin[k] for k in ['provider','project_id','file_id'] if k in origin}})
    from . import client_graphics
    graphics=st.get('client_graphics') or None
    sides=side_choices(st,records)
    return {'runtime':active,'mods':records,'graphics':graphics,'client_sides':sides,'fingerprint':fingerprint(active,records,graphics,sides)}

def fingerprint(active,records,graphics=None,client_sides=None):
    value={'runtime':runtime(active),'mods':sorted((x['filename'],x['hashes']['sha256']) for x in records),'export_policy':EXPORT_POLICY,'exporter_version':__version__}
    if active['loader']=='FABRIC':value['fabric_pack_format']='fabric-loader-v1'
    if graphics:value['client_graphics']=graphics
    if client_sides:value['client_sides']=client_sides
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def server_only(record):
    return record['source']=='system' or any(m['id']=='mcj_guard' for m in record['metadata']['mods']) or record['metadata'].get('environment')=='server'

def side_choices(st,records):
    saved=(st.get('client_mod_sides') if st is not None else None) or {}
    return {r['hashes']['sha256']:saved[r['hashes']['sha256']] for r in records if not server_only(r) and saved.get(r['hashes']['sha256']) in ('required','optional','unsupported')}

def set_side(root,st,sha256,side,basis,actor):
    """Controller owns the observed files and the lock across check and change."""
    if not HEX64.fullmatch(sha256) or side not in ('auto','required','optional','unsupported'):
        raise ValueError('client_pack_side_invalid')
    with st.change_lock():
        observed=snapshot(root,st)
        if observed['fingerprint']!=basis:raise ValueError('client_pack_source_changed')
        record=next((r for r in observed['mods'] if r['hashes']['sha256']==sha256),None)
        if record is None:raise ValueError('client_pack_source_changed')
        if server_only(record):raise ValueError('client_pack_server_only')
        with st.db(immediate=True) as db:
            if db.execute("SELECT 1 FROM jobs WHERE kind='client_pack_build' AND state IN ('queued','running')").fetchone():
                raise ValueError('storage_operation_busy')
            row=db.execute("SELECT value FROM settings WHERE name='client_mod_sides'").fetchone()
            saved=json.loads(row[0]) if row else {}
            # Retain only installed artifacts, so stale versions cannot grow forever.
            saved={r['hashes']['sha256']:saved[r['hashes']['sha256']] for r in observed['mods'] if saved.get(r['hashes']['sha256']) in ('required','optional','unsupported')}
            if side=='auto':saved.pop(sha256,None)
            else:saved[sha256]=side
            db.execute('INSERT INTO settings(name,value,secret) VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',('client_mod_sides',json.dumps(saved)))
        st.event('mods','client_mod_side_changed',actor,{'sha256':sha256,'side':side})
    return {'saved':True}

def patched_bytes(root,sha):
    # An explicitly reviewed LGPL patch is the sole JAR redistributed by us.
    if sha!=CARRY_HASH:raise ValueError('client_pack_file_not_exportable')
    for path in project_path(root,'server/mods').glob('*.jar'):
        raw=read_bounded(path,mods.MAX_JAR)
        if hashlib.sha256(raw).hexdigest()==sha:
            if any(m['id']=='mcj_guard' for m in mods.inspect_jar(raw)['mods']):break
            return {'base64':base64.b64encode(raw).decode(),'sha256':sha}
    raise ValueError('client_pack_file_not_exportable')

def public_url(value):
    parsed=urlparse(value)
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port is not None or parsed.query or parsed.fragment or not (parsed.hostname=='cdn.modrinth.com' or (parsed.hostname or '').endswith('.forgecdn.net')):
        raise ValueError('client_pack_download_not_public')
    return value

def modrinth_record(record,active):
    with httpx.Client(base_url='https://api.modrinth.com/v2',timeout=25,follow_redirects=False,headers={'User-Agent':sources.AGENT}) as client:
        response=client.get('/version_file/'+record['hashes']['sha1'],params={'algorithm':'sha1'})
        if response.status_code==404:return None
        response.raise_for_status();version=response.json()
        if active['version'] not in version['game_versions'] or mods.provider_loader(active) not in version['loaders']:raise ValueError('client_pack_provider_mismatch')
        file=next((x for x in version['files'] if x['hashes'].get('sha512')==record['hashes']['sha512'] and x['hashes'].get('sha1')==record['hashes']['sha1'] and x['size']==record['size']),None)
        if not file:raise ValueError('client_pack_provider_hash_mismatch')
        response=client.get('/project/'+version['project_id']);response.raise_for_status();project=response.json()
    side=project.get('client_side')
    if side not in ['required','optional','unsupported']:return None
    return {'client':side,'url':public_url(file['url']),'license':project.get('license',{}).get('id','unknown'),
            'evidence':'https://modrinth.com/mod/'+project['id'],'provider':'modrinth','project':project['id'],'version':version['id']}

def curseforge_record(st,record,active,explicit_side=None):
    origin=record['origin'];project=origin.get('project_id');file_id=origin.get('file_id')
    if origin.get('provider')!='curseforge' or type(project) is not int or type(file_id) is not int:return None
    if project in CF_BOTH:
        expected,evidence=CF_BOTH[project]
        if expected not in {m['id'] for m in record['metadata']['mods']}:return None
    elif explicit_side in ('required','optional'):
        evidence='https://www.curseforge.com/projects/'+str(project)
    else:
        # CurseForge may declare environments on the exact file (e.g. Client,
        # Server), even when there is no Modrinth record or curated project entry.
        evidence='https://www.curseforge.com/projects/'+str(project)+'/files/'+str(file_id)
    with sources.CurseForge(st) as provider:file=provider.get('/mods/'+str(project)+'/files/'+str(file_id))
    sha=next((x['value'].lower() for x in file.get('hashes',[]) if x['algo']==1),'')
    if file.get('modId')!=project or file.get('id')!=file_id or not file.get('isAvailable') or active['version'] not in file.get('gameVersions',[]) or mods.provider_loader(active) not in [x.lower() for x in file.get('gameVersions',[])] or file['fileLength']!=record['size'] or sha!=record['hashes']['sha1']:
        raise ValueError('client_pack_provider_mismatch')
    if project not in CF_BOTH and not explicit_side:
        environments={x.lower() for x in file.get('gameVersions',[]) if isinstance(x,str)}
        if not {'client','server'}<=environments:return None
    return {'client':explicit_side or 'required','url':public_url(file.get('downloadUrl') or ''),'license':{1651484:'MIT',1683430:'MIT',1680731:'GPL-3.0-only',422301:'All Rights Reserved; official download only',618298:'All Rights Reserved; official download only'}.get(project,'Author terms; official download only'),
            'evidence':evidence,'provider':'curseforge','project':project,'version':file_id}

def classify(st,record,active):
    ids={m['id'] for m in record['metadata']['mods']}
    if server_only(record):
        return {'client':'unsupported','reason':'server_only'}
    explicit=side_choices(st,[record]).get(record['hashes']['sha256'])
    if explicit=='unsupported':return {'client':'unsupported','reason':'administrator_choice','manual':True}
    if record['hashes']['sha256']==CARRY_HASH and ids=={'carryon'} and active.get('version')=='26.3' and active.get('java')==25 and active.get('loader')=='NEOFORGE' and active.get('loader_version') in CARRY_REVIEWED_LOADERS:
        return {'client':explicit or 'required','embedded_patch':True,'license':'LGPL-3.0-or-later','evidence':'https://github.com/Tschipp/CarryOn/tree/168f3fb28fd7ff48d342483142469c3023c54ec0'}
    result=modrinth_record(record,active)
    if result:
        if explicit and result['client']=='unsupported':return {'client':'unknown','reason':'client_pack_provider_side_conflict'}
        if explicit and result['client']!='unsupported':return {**result,'client':explicit,'manual':True}
        return result
    result=curseforge_record(st,record,active,explicit)
    if result:return {**result,**({'manual':True} if explicit else {})}
    return {'client':'unknown','reason':'client_pack_public_source_required' if explicit else 'client_requirements_unknown'}

def dependency_check(records,active):
    from .loader_catalogs import mod_format
    expected_loader=mod_format(active)
    identifiers={'minecraft':active['version'],'java':str(active['java']),('fabricloader' if active['loader']=='FABRIC' else expected_loader.lower()):active['loader_version']}
    proof=active.get('loader_components') or {}
    if active['loader']=='FABRIC' and proof.get('loader_version')==active['loader_version'] and HEX64.fullmatch(proof.get('sha256','')):
        identifiers.update({key:value for key,value in proof.get('components',{}).items() if key!='fabricloader'})
    components=[];issues=[]
    def collect(meta):
        components.append(meta)
        for child in meta.get('embedded',[]):collect(child)
    for record in records:
        if record['metadata']['loader']!=expected_loader:issues.append({'mod':record['filename'],'reason':'loader_mismatch'})
        collect(record['metadata'])
    for meta in components:
        for item in meta['mods']:
            if item['id'] in identifiers and identifiers[item['id']]!=item['version']:issues.append({'mod':item['id'],'reason':'duplicate_mod_id'})
            identifiers[item['id']]=item['version']
        for name in meta.get('provides',[]):identifiers[name]=meta['mods'][0]['version']
    for meta in components:
        matcher=fabric_matches if meta['loader']=='FABRIC' else maven_matches
        for dep in meta.get('dependencies',[]):
            if dep.get('side')=='SERVER' or dep.get('kind')=='discouraged':continue
            actual=identifiers.get(dep['id']);predicate=dep.get('range','')
            if dep.get('kind')=='incompatible':
                if actual is not None and matcher(actual,predicate) is not False:issues.append({'mod':meta['mods'][0]['id'],'dependency':dep['id'],'reason':'conflicting_mod'})
            elif dep.get('mandatory') or actual is not None:
                if actual is None or matcher(actual,predicate) is not True:issues.append({'mod':meta['mods'][0]['id'],'dependency':dep['id'],'reason':'client_dependency_unverified'})
        for conflict in meta.get('breaks',[]):
            if conflict['id'] in identifiers and fabric_matches(identifiers[conflict['id']],conflict['range']) is not False:issues.append({'mod':meta['mods'][0]['id'],'dependency':conflict['id'],'reason':'conflicting_mod'})
    return issues

def create_assets(st):
    with sources.CurseForge(st) as provider:file=provider.get('/mods/328085/files/7963363')
    if file.get('modId')!=328085 or file.get('fileName')!='create-1.21.1-6.0.10.jar' or not file.get('isAvailable'):raise ValueError('client_pack_create_assets_unverified')
    url=public_url(file.get('downloadUrl') or '');raw=sources.download_curseforge(file)
    if hashlib.sha256(raw).hexdigest()!=CREATE_ASSET_HASH:raise ValueError('client_pack_create_assets_unverified')
    return {'path':'config/create-adapted/external-assets/create-1.21.1-6.0.10.jar','hashes':hashes(raw),'fileSize':len(raw),'downloads':[url],'env':{'client':'required','server':'unsupported'}}

def build(st,rpc,actor):
    from . import client_graphics
    first=rpc('/client-pack/snapshot');active=runtime(first['runtime'])
    if active!=runtime(st.get('server')):raise ValueError('client_pack_runtime_unverified')
    graphics=client_graphics.approved(st,active)
    selected=[];excluded=[];report=[];files=[];bundled={}
    for record in first['mods']:
        side=classify(st,record,active)
        if side['client'] in ('required','optional') and graphics and graphics.get('create_compatibility_patch') and any(m['id']=='create' for m in record['metadata']['mods']):
            if record['hashes']['sha256']!=CREATE_ORIGINAL_HASH:raise ValueError('client_create_patch_unverified')
            raw=read_bounded(Path(__file__).parent/'client_pack_resources/Create-Adapted-1.31-MCJ-Iris1.jar',mods.MAX_JAR)
            if hashlib.sha256(raw).hexdigest()!=CREATE_IRIS_HASH:raise ValueError('client_create_patch_unverified')
            record={**record,'filename':'create-adapted-26.3-1.31-mcj-iris1.jar','hashes':hashes(raw),'size':len(raw),'metadata':mods.inspect_jar(raw)}
            side={'client':'required','embedded_create_patch':True,'license':'MIT','evidence':'https://github.com/AlexSensey/create-adapted','note':'Client-only Create/Iris compatibility correction; source and original license included.'}
        public={'filename':record['filename'],'mods':record['metadata']['mods'],'sha256':record['hashes']['sha256'],**side}
        report.append(public)
        if side['client'] not in ['required','optional']:excluded.append(public);continue
        selected.append(record)
        path='mods/'+record['filename']
        if side.get('embedded_create_patch'):
            data=Path(__file__).parent/'client_pack_resources'
            bundled['overrides/'+path]=raw
            for name in ['Create-Iris-Compatibility.java','Create-Iris-Compatibility-Proof.json','Create-Adapted-MIT.txt']:
                bundled['overrides/MCJ-LICENSES/'+name]=read_bounded(data/name,2*1024*1024)
        elif side.get('embedded_patch'):
            value=rpc('/client-pack/patched-file',{'sha256':CARRY_HASH});raw=base64.b64decode(value['base64'],validate=True)
            if hashes(raw)!=record['hashes']:raise ValueError('client_pack_source_changed')
            bundled['overrides/'+path]=raw
            data=Path(__file__).parent/'client_pack_resources'
            for name in ['CarryOn-2.12.0-mcj.1-source.zip','LGPL-3.0.txt','GPL-3.0.txt','CarryOn-NOTICE.txt']:
                bundled['overrides/MCJ-LICENSES/'+name]=read_bounded(data/name,2*1024*1024)
        else:files.append({'path':path,'hashes':record['hashes'],'fileSize':record['size'],'downloads':[side['url']],'env':{'client':side['client'],'server':'unsupported'}})
    graphics=client_graphics.approved(st,active)
    if graphics!=first.get('graphics'):raise ValueError('client_pack_source_changed')
    from . import client_train_fix
    client_train_fix.bundle(graphics,active,selected,report,bundled)
    extras=client_graphics.pack_records(graphics)
    from .versions import runtime_components
    issues=dependency_check(selected+extras,runtime_components(st,active))
    issues.extend({'mod':item['filename'],'reason':item['reason']} for item in report if item.get('reason') in ('client_pack_public_source_required','client_pack_provider_side_conflict'))
    if graphics:
        for item in graphics['files']:
            if any(x['path']==item['path'] for x in files) or 'overrides/'+item['path'] in bundled:raise ValueError('client_graphics_duplicate')
            files.append({k:item[k] for k in ['path','hashes','fileSize','downloads','env']})
        bundled['overrides/config/iris.properties']=('enableShaders=true\nshaderPack='+graphics['shader']+'\n').encode()
        bundled['overrides/MCJ-LICENSES/Complementary-NOTICE.txt']=b'Complementary Reimagined by EminGT / Complementary Development.\nhttps://www.complementary.dev/\nDownloaded unmodified from the official provider. Client pack integration is maintained by the server administrator.\n'
    analysis={'runtime':active,'fingerprint':first['fingerprint'],'mods':report,'graphics':graphics,'issues':issues,'excluded':excluded,'checked':time.time()}
    st.set('client_pack_analysis',analysis)
    if issues:raise ValueError('client_pack_dependencies_blocked')
    if not selected:raise ValueError('client_pack_no_verified_mods')
    if any('create' in {m['id'] for m in r['metadata']['mods']} and r['origin'].get('project_id')==1651484 for r in selected):files.append(create_assets(st))
    if rpc('/client-pack/snapshot')['fingerprint']!=first['fingerprint']:raise ValueError('client_pack_source_changed')
    with st.db() as db:
        previous=db.execute('SELECT * FROM client_packs ORDER BY number DESC LIMIT 1').fetchone()
        existing=db.execute('SELECT id FROM client_packs WHERE fingerprint=? ORDER BY number DESC LIMIT 1',(first['fingerprint'],)).fetchone()
    if existing:return {'id':existing['id'],'already_current':True}
    with st.db() as db:
        history=[json.loads(row['data']).get('number',0) for row in db.execute("SELECT data FROM events WHERE event='client_pack_created'")]
    highest=max([previous['number'] if previous else 0,st.get('client_pack_sequence') or 0,
                 *[value for value in history if type(value) is int and 0<=value<2**31]])
    identifier=secrets.token_hex(16);number=highest+1;version=__version__+'-client.'+str(number)
    before=json.loads(previous['manifest'])['mods'] if previous else []
    old={m['filename']:m['sha256'] for m in before if m['client'] in ['required','optional']};new={r['filename']:r['hashes']['sha256'] for r in selected}
    changes={'added':sorted(new.keys()-old.keys()),'removed':sorted(old.keys()-new.keys()),'changed':sorted(k for k in new.keys()&old.keys() if new[k]!=old[k]),'runtime_changed':not previous or json.loads(previous['manifest'])['runtime']!=active}
    manifest={**analysis,'version':version,'changes':changes,'java_required':active['java']}
    loader_id='fabric-loader' if active['loader']=='FABRIC' else active['loader'].lower()
    index={'formatVersion':1,'game':'minecraft','versionId':version,'name':'MCJ Manager – Client','summary':'Exact approved server mods; Java '+str(active['java'])+' required.','dependencies':{'minecraft':active['version'],loader_id:active['loader_version']},'files':files}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        archive.writestr('modrinth.index.json',json.dumps(index,ensure_ascii=False,indent=2))
        archive.writestr('overrides/MCJ-CLIENT-PACK.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        archive.writestr('overrides/MCJ-LICENSES/MCJ-NOTICE.txt',(Path(__file__).parent/'client_pack_resources/MCJ-NOTICE.txt').read_text(encoding='utf-8'))
        archive.writestr('overrides/MCJ-README.txt', 'Prism Launcher: Add Instance > Import > select this .mrpack.\nMinecraft '+active['version']+' / '+active['loader']+' '+active['loader_version']+' / Java '+str(active['java'])+'.\nMod files are downloaded directly from their official providers and verified by hash.\nVisitor Guard and server configuration are deliberately excluded.\nCarry On patch: corresponding source and license terms are in MCJ-LICENSES.\nCreate Adapted original assets are downloaded into config/create-adapted/external-assets, never into mods.\n')
        for name,raw in bundled.items():archive.writestr(name,raw)
    raw=output.getvalue();folder=st.state/'client-packs';folder.mkdir(exist_ok=True,mode=0o700)
    st.atomic(folder/(identifier+'.mrpack'),raw,0o400)
    with st.db() as db:
        db.execute('INSERT INTO client_packs(id,number,created,actor,fingerprint,sha256,size,manifest) VALUES(?,?,?,?,?,?,?,?)',
            (identifier,number,time.time(),actor,first['fingerprint'],hashlib.sha256(raw).hexdigest(),len(raw),json.dumps(manifest)))
        db.execute('INSERT INTO settings(name,value,secret) VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',
            ('client_pack_sequence',json.dumps(number)))
    st.event('mods','client_pack_created',actor,{'id':identifier,'number':number,'included':len(selected),'excluded':len(excluded)})
    return {'id':identifier,'version':version,'included':len(selected),'excluded':len(excluded)}

def listing(st):
    with st.db() as db:
        counts={x['pack_id']:x['total'] for x in db.execute('''SELECT l.pack_id,COUNT(*) AS total FROM client_pack_links l JOIN users u ON u.id=l.actor
            WHERE l.revoked IS NULL AND (l.expires=0 OR l.expires>?) AND u.enabled=1 AND u.admin=1 GROUP BY l.pack_id''',(time.time(),))}
        packs=[{**{k:x[k] for k in ['id','number','created','sha256','size','fingerprint']},'manifest':json.loads(x['manifest']),'active_links':counts.get(x['id'],0)} for x in db.execute('SELECT * FROM client_packs ORDER BY number DESC LIMIT 30')]
        links=[{**{k:x[k] for k in ['id','pack_id','created','revoked','fingerprint']},'expires':x['expires'] or None,'version':json.loads(x['manifest'])['version']} for x in db.execute('SELECT l.id,l.pack_id,l.created,l.expires,l.revoked,p.fingerprint,p.manifest FROM client_pack_links l JOIN client_packs p ON p.id=l.pack_id ORDER BY l.created DESC LIMIT 100')]
    return {'packs':packs,'links':links,'analysis':st.get('client_pack_analysis') or None}

def archive(st,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('client_pack_not_found')
    with st.db() as db:row=db.execute('SELECT * FROM client_packs WHERE id=?',(identifier,)).fetchone()
    if row is None:raise ValueError('client_pack_not_found')
    path=st.state/'client-packs'/(identifier+'.mrpack');raw=read_bounded(path,16*1024*1024)
    if len(raw)!=row['size'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('client_pack_integrity_failed')
    return path,dict(row)

def share(st,identifier,actor,days):
    if days is not None and (type(days) is not int or not 1<=days<=30):raise ValueError('client_pack_expiry_invalid')
    archive(st,identifier);token=secrets.token_urlsafe(32);key=secrets.token_hex(16);now=time.time();expires=now+days*86400 if days is not None else 0
    with st.db() as db:db.execute('INSERT INTO client_pack_links(id,pack_id,actor,created,expires,token_hash) VALUES(?,?,?,?,?,?)',
        (key,identifier,actor,now,expires,hashlib.sha256(token.encode()).hexdigest()))
    st.event('mods','client_pack_shared',actor,{'id':key,'pack_id':identifier,'days':days})
    return {'id':key,'token':token,'expires':expires or None}

def authorize_share(st,token,current_fingerprint):
    if not isinstance(token,str) or not TOKEN.fullmatch(token):raise ValueError('client_pack_link_invalid')
    digest=hashlib.sha256(token.encode()).hexdigest()
    with st.db() as db:row=db.execute('''SELECT l.*,p.fingerprint,p.manifest FROM client_pack_links l JOIN client_packs p ON p.id=l.pack_id
        JOIN users u ON u.id=l.actor WHERE l.token_hash=? AND l.revoked IS NULL AND (l.expires=0 OR l.expires>?) AND u.enabled=1 AND u.admin=1''',(digest,time.time())).fetchone()
    if row is None:raise ValueError('client_pack_link_invalid')
    if current_fingerprint is not None and row['fingerprint']!=current_fingerprint:raise ValueError('client_pack_outdated')
    result=dict(row);result['expires']=result['expires'] or None;return result


def delete_old(root,st,identifiers,actor,confirmation=None):
    """Check actual installed files and delete under one controller-owned lock."""
    from . import storage_admin
    with st.change_lock():
        observed=snapshot(root,st)['fingerprint']
        return storage_admin.delete(st,st.state/'client-packs','client_pack',identifiers,actor,
                                    confirmation=confirmation,current_fingerprint=observed)

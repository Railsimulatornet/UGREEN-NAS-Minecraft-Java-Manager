"""Bounded pack import. Downloads and configuration remain staged until isolated acceptance."""
from .project_paths import project_path
import contextlib,hashlib,json,os,re,secrets,shutil,zipfile
from pathlib import Path,PurePosixPath
from . import mods,properties,server_settings

MAX_ARCHIVE=512*1024*1024
CONFIG_ROOTS={'config','defaultconfigs','kubejs','scripts','datapacks','resources'}

def entries(archive):
    items=archive.infolist()
    if len(items)>30000 or sum(x.file_size for x in items)>4*1024**3:raise ValueError('pack_expansion_limit')
    seen=set()
    for item in items:
        name=item.filename;path=PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or any(ord(c)<32 for c in name):raise ValueError('pack_unsafe_path')
        if item.flag_bits&1 or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('pack_unsafe_entry')
        normalized=path.as_posix().casefold()
        if normalized in seen:raise ValueError('pack_duplicate_path')
        seen.add(normalized)
    return items

def manifest(archive,server):
    try:return _manifest(archive,server)
    except (KeyError,TypeError,AttributeError,json.JSONDecodeError):raise ValueError('pack_manifest_invalid') from None

def _manifest(archive,server):
    items=entries(archive);names={x.filename:x for x in items}
    if 'manifest.json' not in names:return None
    if names['manifest.json'].file_size>2*1024*1024:raise ValueError('pack_manifest_limit')
    value=json.loads(archive.read('manifest.json'))
    if not isinstance(value,dict):raise ValueError('pack_manifest_invalid')
    if value.get('manifestType')!='minecraftModpack' or value.get('manifestVersion')!=1:raise ValueError('pack_manifest_invalid')
    if value['minecraft']['version']!=server['version']:raise ValueError('pack_game_mismatch')
    loaders=[x['id'] for x in value['minecraft']['modLoaders'] if x.get('primary')]
    prefixes={'FABRIC':'fabric-','FORGE':'forge-','NEOFORGE':'neoforge-'}
    if len(loaders)!=1 or not loaders[0].startswith(prefixes[server['loader']]):raise ValueError('pack_loader_mismatch')
    if not isinstance(value.get('files'),list) or len(value['files'])>512:raise ValueError('pack_mod_count_limit')
    seen=set()
    for file in value['files']:
        if type(file.get('projectID')) is not int or type(file.get('fileID')) is not int or file['projectID']<=0 or file['fileID']<=0:raise ValueError('pack_manifest_invalid')
        if type(file.get('required',True)) is not bool or file['projectID'] in seen:raise ValueError('pack_manifest_invalid')
        seen.add(file['projectID'])
    overrides=value.get('overrides','overrides')
    if not re.fullmatch('[A-Za-z0-9_-]{1,60}',overrides):raise ValueError('pack_manifest_invalid')
    return value

def cache_configuration(store,root,archive,paths,prefix=''):
    result=[];settings={};skipped=[];seen=set()
    for entry in paths:
        if entry.is_dir():continue
        name=entry.filename
        if prefix:
            if not name.startswith(prefix):continue
            name=name[len(prefix):]
        path=PurePosixPath(name)
        if not path.parts:continue
        if name=='server.properties':
            if entry.file_size>65536:raise ValueError('pack_configuration_limit')
            value=properties.loads(archive.read(entry).decode('utf-8'))
            settings={k:v for k,v in value.items() if k not in {*server_settings.PROTECTED,*server_settings.SECRET_KEYS,'level-name'}}
            server_settings.normalize(store.get('server'),{'properties':settings});continue
        if path.parts[0] not in CONFIG_ROOTS:continue
        if name.startswith('config/jei/world/') or path.name.endswith('.bak') or path.name=='sodium-fingerprint.json':
            skipped.append(name);continue
        if path.suffix.casefold() in {'.jar','.exe','.dll','.so','.bat','.sh','.ps1','.cmd','.pem','.key'}:raise ValueError('pack_configuration_type_unsupported')
        if len(path.parts)>20 or entry.file_size>16*1024*1024 or len(result)>=4096:raise ValueError('pack_configuration_limit')
        if name.casefold() in seen:raise ValueError('pack_duplicate_path')
        seen.add(name.casefold());raw=archive.read(entry);checksum=hashlib.sha256(raw).hexdigest()
        store.atomic(project_path(Path(root),'staging/pack-files')/(checksum+'.bin'),raw,0o440)
        result.append({'path':name,'sha256':checksum,'size':len(raw)})
    return result,settings,skipped

def stage_zip(store,root,path,source,provider,project,file):
    from .sources import prepare_curseforge,reference,register_prepared
    prepared=[];server=store.get('server')
    with zipfile.ZipFile(path) as archive:
        checked=entries(archive);document=manifest(archive,server)
        if document:
            roots=[]
            for item in document['files']:
                if not item.get('required',True):continue
                child=provider.get('/mods/'+str(item['projectID']));child_source=reference(child['links']['websiteUrl'])
                if child_source['kind']!='mod':raise ValueError('pack_manifest_invalid')
                child_source.update(file_id=item['fileID'],allow_prerelease=source.get('allow_prerelease',False),root_source_id=source['id'])
                roots.append((child,child_source))
            prepared=prepare_curseforge(store,root,provider,roots,pack_project=project['id'])
            configurations,settings,skipped=cache_configuration(store,root,archive,checked,document['overrides']+'/')
        else:
            # Published dedicated archives can contain complete JARs instead of a launcher manifest.
            if not file.get('isServerPack'):raise ValueError('dedicated_server_pack_unverified')
            files=[x for x in checked if not x.is_dir()]
            roots={PurePosixPath(x.filename).parts[:-2] for x in files if x.filename.endswith('.jar') and len(PurePosixPath(x.filename).parts)>=2 and PurePosixPath(x.filename).parts[-2]=='mods'}
            if len(roots)!=1:raise ValueError('pack_mod_file_invalid')
            prefix='/'.join(next(iter(roots)));prefix=prefix+'/' if prefix else ''
            for entry in files:
                name=entry.filename[len(prefix):] if prefix else entry.filename
                if not name.startswith('mods/') or not name.endswith('.jar'):continue
                if len(PurePosixPath(name).parts)!=2 or entry.file_size>mods.MAX_JAR:raise ValueError('pack_mod_file_invalid')
                item=mods.prepare_jar(store,root,archive.read(entry),PurePosixPath(name).name)
                if item['metadata']['loader']!=server['loader']:raise ValueError('mod_source_loader_mismatch')
                prepared.append({**item,'source':'pack','origin':{'provider':'curseforge_pack','project_id':project['id'],'file_id':file['id'],
                    'pack_project':project['id'],'source_id':source['id'],'url':source['url']}})
            configurations,settings,skipped=cache_configuration(store,root,archive,checked,prefix)
        if not prepared:raise ValueError('pack_contains_no_server_mods')
    with Path(path).open('rb') as stream:archive_sha256=hashlib.file_digest(stream,'sha256').hexdigest()
    raw_plan={'project_id':project['id'],'file_id':file['id'],'name':project['name'],'source_id':source['id'],'files':configurations,
        'properties':settings,'apply_properties':False,'skipped_client_or_backup_files':skipped,'archive_sha256':archive_sha256}
    raw_plan['id']=hashlib.sha256(json.dumps(raw_plan,sort_keys=True).encode()).hexdigest()
    with store.change_lock():
        pending=[x for x in store.get('pack_pending') or [] if x['project_id']!=project['id']]
        if len(pending)>=10:raise ValueError('pack_pending_limit')
        keep={x['id'] for x in prepared};disable=[]
        wanted_ids={m['id'] for x in prepared for m in x['metadata']['mods']}
        with store.db() as db:
            for record in db.execute("SELECT * FROM mods WHERE state NOT IN ('superseded','rejected') AND source!='system'"):
                origin=json.loads(record['origin']) if record['origin'] else {}
                if origin.get('pack_project')==project['id'] and not origin.get('user_override') and record['id'] not in keep:
                    old_ids={x['id'] for x in json.loads(record['metadata'])['mods']}
                    if not old_ids.intersection(wanted_ids):disable.append(record['id'])
        staged=register_prepared(store,prepared,('pack_pending',[*pending,raw_plan]),disable)
    return {'staged':staged,'pending_pack':raw_plan,'installed':False,'live_server_changed':False,'runtime_test':'required'}

def stage_curseforge_pack(store,root,source):
    from .sources import CurseForge,download_curseforge
    path=project_path(Path(root),'staging')/('pack-'+secrets.token_hex(12)+'.zip')
    try:
        with CurseForge(store) as provider:
            project=provider.project(source);file=provider.file(project,source,store.get('server'))
            if file.get('serverPackFileId'):
                server_file=provider.get('/mods/'+str(project['id'])+'/files/'+str(file['serverPackFileId']))
                if server_file.get('modId')!=project['id'] or not server_file.get('isServerPack'):raise ValueError('mod_source_file_unverified')
                file=server_file
            download_curseforge(file,limit=MAX_ARCHIVE,destination=path)
            return stage_zip(store,root,path,source,provider,project,file)
    finally:
        if path.exists():path.unlink()

def stage_uploaded(store,root,path,source_id=None,allow_prerelease=False):
    from .sources import CurseForge,find_source
    with zipfile.ZipFile(path) as archive:value=manifest(archive,store.get('server'))
    with (CurseForge(store) if source_id or value else contextlib.nullcontext(None)) as provider:
        if source_id:
            source=find_source(store,source_id)
            if source['provider']!='curseforge' or source['kind']!='pack':raise ValueError('mod_source_project_unverified')
            project=provider.project(source);file=provider.file(project,source,store.get('server'))
            expected=next((x['value'] for x in file.get('hashes',[]) if x['algo']==1),None)
            with Path(path).open('rb') as stream:actual=hashlib.file_digest(stream,'sha1').hexdigest()
            if not expected or actual!=expected.lower():raise ValueError('mod_download_hash_mismatch')
        else:
            with Path(path).open('rb') as stream:identity=hashlib.file_digest(stream,'sha256').hexdigest()
            source={'id':identity[:24],'url':'','allow_prerelease':allow_prerelease}
            project={'id':'local:'+identity,'name':str((value or {}).get('name','imported_server_pack'))[:120]}
            file={'id':identity,'isServerPack':not bool(value)}
        return stage_zip(store,root,path,source,provider,project,file)

def apply_pending(store,root,data,runtime):
    """Apply only to the disposable candidate. Preserve independently edited configuration."""
    old=store.get('pack_installations') or {};changed=dict(old)
    for plan in store.get('pack_pending') or []:
        previous=old.get(str(plan['project_id']),{}).get('files',{})
        for item in plan['files']:
            relative=PurePosixPath(item['path'])
            if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0] not in CONFIG_ROOTS:raise ValueError('pack_unsafe_path')
            target=Path(data).joinpath(*relative.parts)
            if not target.resolve().is_relative_to(Path(data).resolve()) or target.is_symlink():raise ValueError('pack_unsafe_path')
            if target.exists():
                actual=hashlib.sha256(target.read_bytes()).hexdigest()
                if actual not in [item['sha256'],previous.get(item['path'])]:raise ValueError('pack_own_configuration_conflict')
            source=project_path(Path(root),'staging/pack-files')/(item['sha256']+'.bin')
            if source.is_symlink() or not re.fullmatch('[0-9a-f]{64}',item['sha256']):raise ValueError('staging_integrity_failure')
            raw=source.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['sha256'] or len(raw)!=item['size']:raise ValueError('staging_integrity_failure')
            store.atomic(target,raw,0o600)
        if plan.get('apply_properties'):
            runtime.update(server_settings.normalize(runtime,{'properties':plan['properties']}))
        changed[str(plan['project_id'])]={'file_id':plan['file_id'],'name':plan['name'],'files':{x['path']:x['sha256'] for x in plan['files']}}
    return changed


def restored_state(path):
    """Old archives predate pack tracking; never attach current metadata to them."""
    path=Path(path)
    if not path.exists():return {}
    if path.is_symlink() or path.stat().st_size>8*1024*1024:raise ValueError('pack_backup_state_invalid')
    try:
        document=json.loads(path.read_text(encoding='utf-8'))
        if document.get('format')!=1 or not isinstance(document.get('installations'),dict):raise ValueError()
        value=document['installations']
        if len(value)>100:raise ValueError()
        for item in value.values():
            if not isinstance(item,dict) or not isinstance(item.get('files'),dict) or len(item['files'])>4096:raise ValueError()
            for name,digest in item['files'].items():
                relative=PurePosixPath(name)
                if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name or not relative.parts or relative.parts[0] not in CONFIG_ROOTS:raise ValueError()
                if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError()
        return value
    except (ValueError,TypeError,AttributeError):raise ValueError('pack_backup_state_invalid') from None

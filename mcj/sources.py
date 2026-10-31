"""Official mod-provider adapters. Provider credentials never accompany CDN requests."""
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse,urljoin
import httpx
from . import mods
from .http_identity import AGENT

LOADERS={'FORGE':1,'FABRIC':4,'NEOFORGE':6}

def inventory(store):
    sources=store.get('mod_sources') or []
    with store.db() as db:records=[dict(row) for row in db.execute("SELECT filename,state,installed_enabled,origin FROM mods WHERE state NOT IN ('superseded','rejected')")]
    for source in sources:
        matches=[]
        for row in records:
            origin=json.loads(row['origin'] or '{}')
            try:
                upstream=reference(origin.get('url',''))
                same=all(upstream.get(key)==source.get(key) for key in ('provider','kind','slug'))
            except ValueError:same=False
            if same:matches.append({**row,'origin':origin})
        source['installation']={'active':[row['filename'] for row in matches if row['installed_enabled']],
            'inactive':[row['filename'] for row in matches if row['state']=='installed' and not row['installed_enabled']],
            'pending':[row['filename'] for row in matches if row['state']=='staged'],
            'locally_modified':any(row['origin'].get('provider')=='manual_patch' and row['installed_enabled'] for row in matches)}
    return sources

def reference(value):
    parsed=urlparse(value)
    if parsed.scheme!='https' or parsed.netloc not in ['curseforge.com','www.curseforge.com','modrinth.com'] or parsed.query or parsed.fragment:
        raise ValueError('invalid_mod_source_url')
    if parsed.hostname in ['curseforge.com','www.curseforge.com']:
        match=re.fullmatch(r'/minecraft/(mc-mods|modpacks)/([a-z0-9-]{1,100})(?:/files/(\d{1,12}))?/?',parsed.path)
        if not match:raise ValueError('invalid_mod_source_url')
        kind='pack' if match[1]=='modpacks' else 'mod';provider='curseforge';slug=match[2];file_id=int(match[3]) if match[3] else None
        canonical='https://www.curseforge.com/minecraft/'+match[1]+'/'+slug+('/files/'+str(file_id) if file_id else '')
    elif parsed.hostname=='modrinth.com':
        match=re.fullmatch(r'/mod/([a-zA-Z0-9_-]{1,100})(?:/version/([a-zA-Z0-9]{1,40}))?/?',parsed.path)
        if not match:raise ValueError('invalid_mod_source_url')
        provider='modrinth';kind='mod';slug=match[1];file_id=match[2];canonical='https://modrinth.com/mod/'+slug+('/version/'+file_id if file_id else '')
    else:raise ValueError('invalid_mod_source_url')
    return {'id':hashlib.sha256(canonical.encode()).hexdigest()[:24],'provider':provider,'kind':kind,'slug':slug,'file_id':file_id,'url':canonical}

class CurseForge:
    def __init__(self,store):
        cfg=store.get('providers') or {};key=cfg.get('curseforge_api_key')
        if not key:raise ValueError('curseforge_api_key_required')
        self.client=httpx.Client(base_url='https://api.curseforge.com/v1',timeout=25,follow_redirects=False,
            headers={'User-Agent':AGENT,'Accept':'application/json','x-api-key':key})
    def __enter__(self):return self
    def __exit__(self,*args):self.client.close()
    def get(self,path,params=None):
        response=self.client.get(path,params=params)
        if response.status_code in [401,403]:raise ValueError('curseforge_access_denied')
        response.raise_for_status()
        if len(response.content)>8*1024*1024:raise ValueError('provider_metadata_limit')
        return response.json()['data']
    def project(self,source):
        candidates=self.get('/mods/search',{'gameId':432,'slug':source['slug'],'pageSize':50})
        matches=[]
        for candidate in candidates:
            try:link=reference(candidate['links']['websiteUrl'])
            except (ValueError,KeyError):continue
            if link['kind']==source['kind'] and link['slug']==source['slug'] and candidate['gameId']==432:matches.append(candidate)
        if len(matches)!=1:raise ValueError('mod_source_project_unverified')
        return matches[0]
    def file(self,project,source,server):
        if source.get('file_id'):file=self.get('/mods/'+str(project['id'])+'/files/'+str(source['file_id']))
        else:
            params={'gameVersion':server['version'],'pageSize':50}
            if source['kind']=='mod':params['modLoaderType']=LOADERS[server['loader']]
            files=self.get('/mods/'+str(project['id'])+'/files',params)
            allowed=[1,2] if source.get('allow_prerelease') else [1]
            files=[x for x in files if x.get('releaseType') in allowed and x.get('isAvailable') and not x.get('isEarlyAccessContent')]
            files.sort(key=lambda x:x['fileDate'],reverse=True)
            if not files:raise ValueError('no_stable_compatible_version')
            file=files[0]
        if file['modId']!=project['id'] or file.get('releaseType') not in ([1,2] if source.get('allow_prerelease') else [1]) or not file.get('isAvailable') or file.get('isEarlyAccessContent'):
            raise ValueError('mod_source_file_unverified')
        if server['version'] not in file.get('gameVersions',[]):raise ValueError('mod_source_game_mismatch')
        if source['kind']=='mod' and server['loader'].lower() not in [x.lower() for x in file.get('gameVersions',[])]:raise ValueError('mod_source_loader_mismatch')
        return file

def inspect_source(store,source):
    server=store.get('server')
    if source['provider']=='curseforge':
        with CurseForge(store) as provider:
            project=provider.project(source);file=provider.file(project,source,server)
        dedicated=bool(file.get('isServerPack') or file.get('serverPackFileId'))
        report={'provider':'curseforge','project_id':project['id'],'name':project['name'],'file_id':file['id'],
                'file_name':file['fileName'],'version':file['displayName'],'game_versions':file['gameVersions'],'prerelease':file['releaseType']!=1,
                'dedicated_server_pack':'published' if dedicated else 'unverified','download_permitted':bool(file.get('downloadUrl')),
                'required_projects':[x['modId'] for x in file.get('dependencies',[]) if x['relationType']==3]}
        report['state']='metadata_checked'
        if source['kind']=='pack' and not dedicated:report['dedicated_server_pack']='not_published'
    else:
        with httpx.Client(base_url='https://api.modrinth.com/v2',timeout=25,follow_redirects=False,headers={'User-Agent':AGENT}) as client:
            response=client.get('/project/'+source['slug']);response.raise_for_status();project=response.json()
            if project.get('project_type')!='mod':raise ValueError('mod_source_project_unverified')
            if source.get('file_id'):
                response=client.get('/version/'+source['file_id']);response.raise_for_status();versions=[response.json()]
            else:
                response=client.get('/project/'+project['id']+'/version',params={'loaders':json.dumps([server['loader'].lower()]),'game_versions':json.dumps([server['version']])})
                response.raise_for_status();versions=response.json()
            versions=[x for x in versions if x['project_id']==project['id'] and x['version_type']=='release' and server['version'] in x['game_versions'] and server['loader'].lower() in x['loaders']]
            versions.sort(key=lambda x:x['date_published'],reverse=True)
            if not versions:raise ValueError('no_stable_compatible_version')
            version=versions[0]
        report={'provider':'modrinth','project_id':project['id'],'name':project['title'],'file_id':version['id'],'version':version['version_number'],'state':'metadata_checked'}
    return {**report,'checked':time.time(),'source_id':source['id'],'live_server_changed':False,'runtime_test':'not_tested'}

def download_curseforge(file,limit=mods.MAX_JAR,destination=None):
    url=file.get('downloadUrl') or '';parsed=urlparse(url)
    if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.forgecdn.net') or parsed.username or parsed.password or parsed.port is not None or parsed.fragment:
        raise ValueError('curseforge_download_not_permitted')
    expected=next((x['value'] for x in file.get('hashes',[]) if x['algo']==1),None)
    if not expected or not re.fullmatch('[0-9a-fA-F]{40}',expected):raise ValueError('mod_download_hash_missing')
    size=file.get('fileLength')
    if type(size) is not int or not 0<size<=limit:raise ValueError('provider_file_too_large')
    digest=hashlib.sha1();total=0;data=bytearray();output=None
    try:
        if destination:output=Path(destination).open('xb')
        # A separate client is essential: never forward x-api-key to a download host.
        with httpx.Client(timeout=45,follow_redirects=False,headers={'User-Agent':AGENT}) as client:
            for _ in range(4):
                with client.stream('GET',url) as response:
                    if response.status_code in [301,302,303,307,308]:
                        url=urljoin(url,response.headers.get('location',''));parsed=urlparse(url)
                        if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.forgecdn.net') or parsed.username or parsed.password or parsed.port is not None or parsed.fragment:
                            raise ValueError('mod_download_source_invalid')
                        continue
                    response.raise_for_status()
                    for part in response.iter_bytes(65536):
                        total+=len(part)
                        if total>size or total>limit:raise ValueError('provider_file_too_large')
                        digest.update(part)
                        if output:output.write(part)
                        else:data.extend(part)
                    break
            else:raise ValueError('provider_redirect_limit')
        if total!=size or digest.hexdigest()!=expected.lower():raise ValueError('mod_download_hash_mismatch')
        return bytes(data) if output is None else {'size':total,'sha1':digest.hexdigest()}
    finally:
        if output:output.close()

def register_prepared(store,prepared,setting=None,disable=()):
    results=[];observed={}
    with store.change_lock(),store.db(immediate=True) as db:
        records=mods.proposed_records([dict(x) for x in db.execute("SELECT * FROM mods WHERE state!='superseded'")])
        for item in prepared:
            metadata=item['metadata'];identifiers={x['id'] for x in metadata['mods']}
            for identifier in identifiers:
                if identifier in observed and observed[identifier]!=item['id']:raise ValueError('duplicate_mod_id')
                observed[identifier]=item['id']
            matches=[x for x in records if {m['id'] for m in json.loads(x['metadata'])['mods']}==identifiers]
            if len(matches)>1:raise ValueError('mod_identity_ambiguous')
            previous=matches[0] if matches else None
            if previous and previous.get('remove_pending') is not None:raise ValueError('mod_removal_pending')
            if previous and previous['sha256']==item['id']:
                result={'id':previous['id'],'already_present':True,'enabled':bool(previous['enabled']),'installed':bool(previous['installed_enabled'])}
                # The provider download was verified before registration. Associate
                # its exact hash with an earlier upload without reinstalling it or
                # replacing an existing provider choice, patch, or system record.
                origin=item.get('origin') or {}
                if (previous['source'] in ('upload','manual','unmanaged') and not json.loads(previous.get('origin') or '{}')
                    and 'mcj_guard' not in identifiers and origin.get('provider') in ('curseforge','modrinth')
                    and item['source']==origin['provider']):
                    db.execute('UPDATE mods SET source=?,origin=?,available=NULL,updated=? WHERE id=?',
                               (item['source'],json.dumps(origin),time.time(),previous['id']))
                    result['source_linked']=True
                results.append(result);continue
            if (previous and previous['source']=='system') or 'mcj_guard' in identifiers:raise ValueError('visitor_guard_is_protected')
            if item['origin'].get('pack_project') and previous:
                old_origin=json.loads(previous['origin']) if previous.get('origin') else {}
                if old_origin.get('pack_project')!=item['origin']['pack_project']:raise ValueError('pack_own_mod_conflict')
                if old_origin.get('user_override') and not item['origin'].get('user_override'):
                    results.append({'id':previous['id'],'skipped_user_override':True,'enabled':bool(previous['enabled'])});continue
            existing=db.execute('SELECT * FROM mods WHERE id=?',(item['id'],)).fetchone()
            if existing and existing['installed_enabled']:raise ValueError('pending_mod_update_conflict')
            enabled=previous['enabled'] if previous else (existing['enabled'] if existing else int(not metadata['client_only_hint']))
            db.execute('''INSERT INTO mods(id,filename,sha256,metadata,source,state,enabled,updated,replaces,origin)
                VALUES(?,?,?,?,?,'staged',?,?,?,?) ON CONFLICT(id) DO UPDATE SET state='staged',
                source=excluded.source,enabled=excluded.enabled,updated=excluded.updated,replaces=excluded.replaces,
                origin=excluded.origin,installed_enabled=0,error=NULL''',
                (item['id'],item['filename'],item['id'],json.dumps(metadata),item['source'],int(enabled),time.time(),
                 previous['id'] if previous else None,json.dumps(item['origin'])))
            results.append({'id':item['id'],'filename':item['filename'],'enabled':bool(enabled),'installed':False})
        for identifier in disable:db.execute('UPDATE mods SET enabled=0,updated=? WHERE id=? AND source!=?',(time.time(),identifier,'system'))
        if setting:
            name,value=setting
            db.execute('INSERT INTO settings VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',(name,json.dumps(value)))
    return results

def stage_source(store,root,source):
    prepared=[]
    if source['kind']=='pack':
        from .packs import stage_curseforge_pack
        return stage_curseforge_pack(store,root,source)
    if source['provider']=='curseforge':
        with CurseForge(store) as provider:
            prepared=prepare_curseforge(store,root,provider,[(provider.project(source),source)])
    else:
        report=inspect_source(store,source)
        with httpx.Client(base_url='https://api.modrinth.com/v2',timeout=30,follow_redirects=False,headers={'User-Agent':AGENT}) as client:
            response=client.get('/version/'+report['file_id']);response.raise_for_status();version=response.json()
            files=[x for x in version['files'] if x.get('primary') and x['filename'].endswith('.jar')]
            if len(files)!=1:raise ValueError('mod_primary_file_unverified')
            raw=mods.download_modrinth(client,files[0])
        prepared.append({**mods.prepare_jar(store,root,raw,files[0]['filename']),'source':'modrinth',
            'origin':{'provider':'modrinth','project_id':report['project_id'],'file_id':report['file_id'],'url':source['url']}})
    staged=register_prepared(store,prepared)
    store.event('mods','source_files_staged',data={'source_id':source['id'],'count':len(staged)})
    return {'staged':staged,'installed':False,'live_server_changed':False}


def component_versions(metadata):
    found={x['id']:x['version'] for x in metadata['mods']}
    found.update({alias:metadata['mods'][0]['version'] for alias in metadata.get('provides',[])})
    for child in metadata.get('embedded',[]):found.update(component_versions(child))
    return found


def prepare_curseforge(store,root,provider,roots,pack_project=None):
    """Resolve official required projects without registering a half-downloaded set."""
    server=store.get('server');visited={};prepared=[]
    with store.db() as db:known=mods.proposed_records([dict(x) for x in db.execute("SELECT * FROM mods WHERE state NOT IN ('rejected','superseded')")])
    known_versions={}
    for record in known:
        if record['enabled']:known_versions.update(component_versions(json.loads(record['metadata'])))
    known_versions.update({'minecraft':server['version'],'java':str(server.get('java',25)),
        'fabricloader' if server['loader']=='FABRIC' else server['loader'].lower():server.get('loader_version','unknown')})
    known_versions.update(((store.get('loader_components') or {}).get(server.get('loader_version')) or {}).get('components',{}))
    def supplied(metadata,available,parent):
        from .version_ranges import matches as fabric_matches
        from .maven_ranges import matches as maven_matches
        matches=fabric_matches if parent.get('loader')=='FABRIC' else maven_matches
        for module in metadata['mods']:
            actual=available.get(module['id'])
            requirements=[d['range'] for d in parent.get('dependencies',[]) if d.get('mandatory') and d['id']==module['id']]
            if actual is None:return False
            if requirements and any(matches(actual,x) is not True for x in requirements):return False
            if not requirements and actual!=module['version']:return False
        return True
    def prepare(project,source,depth=0,parent=None):
        if depth>10 or len(visited)>=512:raise ValueError('mod_dependency_limit')
        file=provider.file(project,source,server);identity=(project['id'],file['id'])
        if identity in visited:return
        raw=download_curseforge(file);item=mods.prepare_jar(store,root,raw,file['fileName']);metadata=item['metadata']
        visited[identity]=item
        available={**known_versions,**component_versions(parent or {'mods':[]})}
        if parent and supplied(metadata,available,parent):return
        origin={'provider':'curseforge','project_id':project['id'],'file_id':file['id'],'url':source['url'],
                'source_id':source.get('root_source_id',source.get('id')),'allow_prerelease':bool(source.get('allow_prerelease')),
                'prerelease':file['releaseType']!=1,'pinned':bool(source.get('pinned',False))}
        if pack_project:origin['pack_project']=pack_project
        prepared.append({**item,'source':'curseforge','origin':origin})
        if metadata['client_only_hint']:return
        for dependency in file.get('dependencies',[]):
            if dependency['relationType']!=3:continue
            child=provider.get('/mods/'+str(dependency['modId']));child_source=reference(child['links']['websiteUrl'])
            if child_source['kind']!='mod':raise ValueError('mod_source_project_unverified')
            child_source.update(allow_prerelease=source.get('allow_prerelease',False),root_source_id=origin['source_id'])
            prepare(child,child_source,depth+1,metadata)
        for dependency in metadata['dependencies']:
            available={**known_versions,**component_versions(metadata)}
            for candidate in prepared:available.update(component_versions(candidate['metadata']))
            if not dependency.get('mandatory') or dependency.get('side')=='CLIENT' or dependency['id'] in available:continue
            candidates=provider.get('/mods/search',{'gameId':432,'slug':dependency['id'].replace('_','-'),'pageSize':50})
            candidates=[x for x in candidates if x.get('slug')==dependency['id'].replace('_','-') and '/mc-mods/' in x.get('links',{}).get('websiteUrl','')]
            if len(candidates)!=1:continue
            child=candidates[0];child_source=reference(child['links']['websiteUrl']);child_source.update(allow_prerelease=source.get('allow_prerelease',False),root_source_id=origin['source_id'])
            prepare(child,child_source,depth+1,metadata)
    for project,source in roots:
        source={**source,'pinned':bool(source.get('file_id'))};prepare(project,source)
    return prepared


def save_list(store,values):
    if not isinstance(values,list) or len(values)>100:raise ValueError('too_many_mod_sources')
    current={x['id']:x for x in store.get('mod_sources') or []};clean=[];seen=set()
    for value in values:
        if not isinstance(value,dict) or set(value)-{'url','enabled','allow_prerelease'}:raise ValueError('invalid_mod_source_url')
        source=reference(value.get('url',''))
        if source['id'] in seen:raise ValueError('duplicate_mod_source')
        if type(value.get('enabled',True)) is not bool or type(value.get('allow_prerelease',False)) is not bool:raise ValueError('invalid_mod_source_url')
        seen.add(source['id']);source.update(enabled=value.get('enabled',True),allow_prerelease=value.get('allow_prerelease',False))
        old=current.get(source['id'])
        if old and old.get('allow_prerelease',False)==source['allow_prerelease'] and old.get('report'):source['report']=old['report']
        clean.append(source)
    with store.change_lock():store.set('mod_sources',clean)
    return clean


def find_source(store,identifier):
    matches=[x for x in store.get('mod_sources') or [] if x['id']==identifier]
    if len(matches)!=1:raise ValueError('mod_source_unavailable')
    return matches[0]


def check_source(store,identifier):
    source=find_source(store,identifier)
    try:report=inspect_source(store,source)
    except ValueError as exc:report={'state':'blocked','reason':str(exc),'checked':time.time(),'runtime_test':'not_tested'}
    except httpx.HTTPError:report={'state':'unavailable','reason':'mod_provider_unavailable','checked':time.time(),'runtime_test':'not_tested'}
    with store.change_lock():
        current=store.get('mod_sources') or []
        for item in current:
            if item['id']==identifier and item.get('allow_prerelease',False)==source.get('allow_prerelease',False):item['report']=report
        store.set('mod_sources',current)
    return report


def check_updates(store):
    mods.check_modrinth(store)
    with store.db() as db:records=[dict(x) for x in db.execute("SELECT * FROM mods WHERE state NOT IN ('superseded','rejected') AND source!='system'")]
    provider_records=[]
    for record in records:
        origin=json.loads(record['origin']) if record.get('origin') else {}
        if origin.get('provider')=='curseforge':provider_records.append((record,origin))
    if provider_records:
        with CurseForge(store) as api:
            for record,origin in provider_records:
                try:
                    if origin.get('pinned') and not origin.get('pack_project'):result={'status':'pinned','version':None}
                    else:
                        project=api.get('/mods/'+str(origin['project_id']));source=reference(origin['url']);source.update(file_id=None,allow_prerelease=origin.get('allow_prerelease',False))
                        file=api.file(project,source,store.get('server'))
                        result={'status':'current' if file['id']==origin['file_id'] else 'available','version':file['displayName'],
                                'curseforge_file_id':file['id'],'project_id':project['id'],'prerelease':file['releaseType']!=1}
                except (ValueError,httpx.HTTPError):result={'status':'check_failed','version':None}
                with store.db() as db:db.execute('UPDATE mods SET available=?,updated=? WHERE id=?',(json.dumps(result),time.time(),record['id']))
    for source in store.get('mod_sources') or []:
        if source['enabled']:check_source(store,source['id'])
    # Notify only after all providers were checked, including CurseForge.
    with store.db() as db:
        statuses=[]
        for row in db.execute("SELECT available FROM mods WHERE state NOT IN ('superseded','rejected') AND source!='system'"):
            try:result=json.loads(row['available'] or '{}')
            except (TypeError,ValueError):result={}
            value=result.get('status') if isinstance(result,dict) else None
            statuses.append(value if isinstance(value,str) else None)
    store.event('mods','update_check_completed',data={
        'checked':len(statuses),'updates':statuses.count('available'),'failed':statuses.count('check_failed'),
        'unresolved':sum(value not in {'current','available','check_failed','pinned','locally_patched','system_managed'} for value in statuses)})


def stage_update(store,root,identifier):
    with store.db() as db:row=db.execute('SELECT * FROM mods WHERE id=?',(identifier,)).fetchone()
    if not row:raise ValueError('mod_unavailable')
    record=dict(row);origin=json.loads(record['origin']) if record.get('origin') else {}
    if record.get('remove_pending') is not None:raise ValueError('mod_removal_pending')
    if origin.get('provider')!='curseforge':return mods.stage_modrinth_update(store,root,identifier)
    if record['source']=='system' or record['state'] in ['superseded','rejected']:raise ValueError('mod_unavailable')
    source=reference(origin['url']);source.update(file_id=None,allow_prerelease=origin.get('allow_prerelease',False))
    if origin.get('pack_project'):
        with CurseForge(store) as provider:
            prepared=prepare_curseforge(store,root,provider,[(provider.project(source),source)],pack_project=origin['pack_project'])
        for item in prepared:
            if item['origin']['project_id']==origin['project_id']:item['origin']['user_override']=True
        return {'staged':register_prepared(store,prepared),'installed':False,'live_server_changed':False}
    if origin.get('pinned'):raise ValueError('mod_update_unavailable')
    return stage_source(store,root,source)


def search_curseforge(store, query, offset=0):
    """Official Minecraft mod search; each offered file is checked for this runtime."""
    query=query.strip() if isinstance(query,str) else ''
    if not 2<=len(query)<=120 or any(ord(c)<32 for c in query) or type(offset) is not int or not 0<=offset<=9992:
        raise ValueError('invalid_mod_search')
    server=store.get('server');basis={k:server[k] for k in ['version','loader','loader_version']}
    key=hashlib.sha256(json.dumps([query.casefold(),offset,basis],sort_keys=True).encode()).hexdigest()
    cached=store.get('curseforge_search_cache') or {}
    if cached.get('key')==key and time.time()-cached.get('at',0)<300:return cached['result']
    results=[]
    with CurseForge(store) as provider:
        candidates=provider.get('/mods/search',{'gameId':432,'classId':6,'gameVersion':server['version'],
            'modLoaderType':LOADERS[server['loader']],'searchFilter':query,'pageSize':8,'index':offset,
            'sortField':2,'sortOrder':'desc'})
        for project in candidates[:8]:
            try:
                if project.get('gameId')!=432 or project.get('classId')!=6:continue
                source=reference(project['links']['websiteUrl'])
                if source['kind']!='mod' or source['provider']!='curseforge':continue
                file=provider.file(project,{**source,'allow_prerelease':False},server)
                if not isinstance(file.get('id'),int):continue
                results.append({'project_id':project['id'],'file_id':file['id'],'name':str(project['name'])[:200],
                    'summary':str(project.get('summary',''))[:500],'url':source['url'],'version':str(file['displayName'])[:200],
                    'filename':file['fileName'],'size':file.get('fileLength'),
                    'authors':[str(x['name'])[:100] for x in project.get('authors',[])[:3] if isinstance(x.get('name'),str)],
                    'required_projects':[x['modId'] for x in file.get('dependencies',[]) if x.get('relationType')==3],
                    'download_permitted':bool(file.get('downloadUrl')),'runtime_test':'not_tested'})
            except (KeyError,TypeError,ValueError):continue
    result={'query':query,'basis':basis,'results':results,'next_offset':offset+8 if len(candidates)==8 and offset+8<=9992 else None,'checked':time.time()}
    store.set('curseforge_search_cache',{'key':key,'at':time.time(),'result':result})
    return result


def stage_curseforge_selection(store, root, project_id, file_id, basis):
    current=store.get('server')
    if basis!={k:current[k] for k in ['version','loader','loader_version']}:raise ValueError('mod_search_runtime_changed')
    with CurseForge(store) as provider:
        project=provider.get('/mods/'+str(project_id))
        if project.get('id')!=project_id or project.get('gameId')!=432 or project.get('classId')!=6:
            raise ValueError('mod_source_project_unverified')
        source=reference(project['links']['websiteUrl'])
        if source['provider']!='curseforge' or source['kind']!='mod':raise ValueError('mod_source_project_unverified')
        source.update(file_id=file_id,allow_prerelease=False)
        prepared=prepare_curseforge(store,root,provider,[(project,source)])
    # Exact file selection is verified above; future checks may offer newer stable releases.
    for item in prepared:
        if item['origin']['project_id']==project_id:
            item['origin'].update(pinned=False,url=reference(project['links']['websiteUrl'])['url'])
    return register_prepared(store,prepared)

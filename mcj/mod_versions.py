"""Explicit provider-version choices use the existing verified staging pipeline."""
import hashlib,json,re
import httpx
from . import sources

def record(store,identifier):
    with store.db() as db:
        row=db.execute("SELECT * FROM mods WHERE id=? AND state='installed'",(identifier,)).fetchone()
        pending=db.execute("SELECT 1 FROM mods WHERE replaces=? AND state='staged'",(identifier,)).fetchone()
    if not row:raise ValueError('mod_unavailable')
    value=dict(row)
    if value['source']=='system':raise ValueError('visitor_guard_is_protected')
    if value.get('remove_pending') is not None:raise ValueError('mod_removal_pending')
    if pending:raise ValueError('mod_update_pending')
    origin=json.loads(value.get('origin') or '{}')
    try:source=sources.reference(origin.get('url',''))
    except ValueError:raise ValueError('mod_version_source_unknown') from None
    if source['kind']!='mod':raise ValueError('mod_version_source_unknown')
    source['allow_prerelease']=False
    return value,source

def basis(store,identifier):
    runtime=store.get('server')
    return hashlib.sha256(json.dumps([identifier,*[runtime[k] for k in ['version','loader','loader_version']]],separators=(',',':')).encode()).hexdigest()

def catalog(store,identifier,offset=0):
    row,source=record(store,identifier);server=store.get('server');choices=[];next_offset=None
    if type(offset) is not int or not 0<=offset<=10000:raise ValueError('invalid_mod_version_offset')
    if source['provider']=='curseforge':
        with sources.CurseForge(store) as provider:
            project=provider.project(source)
            files=provider.get('/mods/'+str(project['id'])+'/files',{'gameVersion':server['version'],'modLoaderType':sources.LOADERS[server['loader']],'pageSize':20,'index':offset})
        if len(files)==20:next_offset=offset+20
        for file in files:
            if file.get('modId')!=project['id'] or file.get('releaseType')!=1 or not file.get('isAvailable') or file.get('isEarlyAccessContent'):continue
            if server['version'] not in file.get('gameVersions',[]) or server['loader'].lower() not in [x.lower() for x in file.get('gameVersions',[])]:continue
            choices.append({'id':str(file['id']),'name':str(file['displayName'])[:300],'filename':str(file['fileName'])[:300],'published':file.get('fileDate')})
    else:
        with httpx.Client(base_url='https://api.modrinth.com/v2',timeout=25,follow_redirects=False,headers={'User-Agent':sources.AGENT}) as client:
            response=client.get('/project/'+source['slug']);response.raise_for_status();project=response.json()
            if project.get('project_type')!='mod':raise ValueError('mod_source_project_unverified')
            response=client.get('/project/'+project['id']+'/version',params={'loaders':json.dumps([server['loader'].lower()]),'game_versions':json.dumps([server['version']])});response.raise_for_status()
            if len(response.content)>8*1024**2:raise ValueError('provider_metadata_limit')
            all_files=[v for v in response.json() if v.get('project_id')==project['id'] and v.get('version_type')=='release' and server['version'] in v.get('game_versions',[]) and server['loader'].lower() in v.get('loaders',[])]
            all_files.sort(key=lambda v:v.get('date_published',''),reverse=True)
            for version in all_files[offset:offset+20]:
                files=[file for file in version['files'] if file.get('primary') and file.get('filename','').endswith('.jar')]
                if len(files)==1:choices.append({'id':version['id'],'name':str(version['version_number'])[:300],'filename':files[0]['filename'],'published':version.get('date_published')})
            if offset+20<len(all_files):next_offset=offset+20
    return {'versions':choices,'next_offset':next_offset,'basis':basis(store,identifier),'provider':source['provider'],'current_filename':row['filename'],
            'locally_modified':json.loads(row.get('origin') or '{}').get('provider')=='manual_patch',
            'current_id':str(json.loads(row.get('origin') or '{}').get('file_id',''))}

def stage(store,root,identifier,version,expected_basis,pin=True):
    with store.change_lock():return _stage(store,root,identifier,version,expected_basis,pin)

def _stage(store,root,identifier,version,expected_basis,pin):
    if type(pin) is not bool:raise ValueError('invalid_mod_version')
    row,source=record(store,identifier)
    if basis(store,identifier)!=expected_basis:raise ValueError('mod_search_runtime_changed')
    if source['provider']=='curseforge':
        if not re.fullmatch(r'[1-9][0-9]{0,11}',version):raise ValueError('invalid_mod_version')
        source['file_id']=int(version)
    else:
        if not re.fullmatch(r'[A-Za-z0-9]{1,40}',version):raise ValueError('invalid_mod_version')
        source['file_id']=version
    source['url']=('https://www.curseforge.com/minecraft/mc-mods/' if source['provider']=='curseforge' else 'https://modrinth.com/mod/')+source['slug']
    # Pinned provider validation, hashes and dependency resolution run again.
    result=sources.stage_source(store,root,source)
    original_ids={item['id'] for item in json.loads(row['metadata'])['mods']}
    with store.db(immediate=True) as db:
        for item in result['staged']:
            current=db.execute('SELECT metadata,origin FROM mods WHERE id=?',(item['id'],)).fetchone()
            if {part['id'] for part in json.loads(current['metadata'])['mods']}!=original_ids:continue
            origin=json.loads(current['origin'] or '{}');origin['pinned']=pin
            db.execute('UPDATE mods SET origin=?,available=? WHERE id=?',(json.dumps(origin),json.dumps({'status':'pinned','version':None}) if pin else None,item['id']))
    store.event('mods','mod_version_staged',data={'id':identifier,'provider':source['provider'],'version':version})
    return result

from .project_paths import project_path
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
import tomllib
import zipfile
import httpx
from urllib.parse import urlparse
from .version_ranges import matches,Version
from .maven_ranges import matches as maven_matches
from .http_identity import AGENT


def provider_loader(server):
    from .loader_catalogs import mod_format
    return mod_format(server).lower()

MAX_JAR=64*1024*1024
CLIENT_ONLY={'oculus','embeddium','essential','entity_model_features','entity_texture_features','continuity','replaymod','sound_physics_remastered'}

def inspect_jar(raw,_depth=0,_budget=None,preferred_loader=None):
    if len(raw)>MAX_JAR:raise ValueError('jar_too_large')
    if _depth>3:raise ValueError('jar_nesting_limit')
    _budget=_budget if _budget is not None else [0]
    try:
        archive=zipfile.ZipFile(io.BytesIO(raw))
        entries=archive.infolist()
        if len(entries)>20000 or sum(x.file_size for x in entries)>512*1024*1024:raise ValueError('jar_expansion_limit')
        _budget[0]+=sum(x.file_size for x in entries)
        if _budget[0]>512*1024*1024:raise ValueError('jar_expansion_limit')
        if len({x.filename for x in entries})!=len(entries):raise ValueError('jar_duplicate_entry')
        for item in entries:
            path=PurePosixPath(item.filename.replace('\\','/'))
            # A flat license document may contain a colon in a JAR resource name.
            # JARs are kept intact, never extracted; drive paths and ADS stay blocked.
            license_document=item.file_size<=65536 and re.fullmatch(r'[A-Za-z0-9 _-]{2,80}: [A-Za-z0-9 _-]{0,80}(?:LICENSE|NOTICE)\.(?:md|txt)',item.filename,re.I)
            if path.is_absolute() or '..' in path.parts or (':' in item.filename and not license_document) or '\x00' in item.filename:
                raise ValueError('jar_unsafe_path')
            if item.flag_bits & 1:raise ValueError('encrypted_jar_not_supported')
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('jar_symlink')
        names={x.filename:x for x in entries}
        def read(name):
            if name not in names:return None
            if names[name].file_size>1024*1024:raise ValueError('jar_metadata_limit')
            return archive.read(name)
        manifest=read('META-INF/MANIFEST.MF') or b''
        implementation=re.search(rb'^Implementation-Version:\s*([^\r\n]+)',manifest,re.M)
        implementation=implementation[1].decode('utf-8','replace') if implementation else 'unknown'
        if 'fabric.mod.json' in names and not (preferred_loader=='NEOFORGE' and 'META-INF/neoforge.mods.toml' in names):
            data=json.loads(read('fabric.mod.json'))
            if not isinstance(data.get('provides',[]),list) or len(data.get('provides',[]))>256 or any(not isinstance(x,str) or not re.fullmatch('[a-z][a-z0-9_-]{1,79}',x) for x in data.get('provides',[])):
                raise ValueError('jar_invalid_provided_mod_id')
            result={'loader':'FABRIC','mods':[{'id':data['id'],'name':data.get('name',data['id']),'version':data.get('version','unknown')}],
                    'dependencies':[{'id':k,'range':v,'mandatory':True} for k,v in data.get('depends',{}).items()],
                    'environment':data.get('environment','*'),
                    'provides':data.get('provides',[]),
                    'breaks':[{'id':k,'range':v} for k,v in data.get('breaks',{}).items()],
                    'embedded':[]}
            if len(data.get('jars',[]))>256:raise ValueError('jar_nesting_limit')
            for nested in data.get('jars',[]):
                filename=nested['file']
                if filename not in names or names[filename].file_size>MAX_JAR:raise ValueError('jar_nested_file_invalid')
                result['embedded'].append(inspect_jar(archive.read(filename),_depth+1,_budget))
        elif 'META-INF/mods.toml' in names or 'META-INF/neoforge.mods.toml' in names:
            name='META-INF/neoforge.mods.toml' if 'META-INF/neoforge.mods.toml' in names and preferred_loader=='NEOFORGE' else ('META-INF/mods.toml' if 'META-INF/mods.toml' in names else 'META-INF/neoforge.mods.toml')
            data=tomllib.loads(read(name).decode('utf-8'))
            mods=[{'id':x['modId'],'name':x.get('displayName',x['modId']),
                   'version':str(x.get('version','unknown')).replace('${file.jarVersion}',implementation)} for x in data.get('mods',[])]
            result={'loader':'NEOFORGE' if 'neoforge' in name else 'FORGE','mods':mods,
                    'dependencies':[{'id':d['modId'],'range':d.get('versionRange',''),
                                     'mandatory':d.get('mandatory',d.get('type')=='required'),'side':d.get('side','BOTH'),
                                     'kind':d.get('type','required' if d.get('mandatory') else 'optional')}
                                    for values in data.get('dependencies',{}).values() for d in values],
                    'environment':'unknown','embedded':[],'embedded_libraries':[]}
            if 'META-INF/jarjar/metadata.json' in names:
                bundled=json.loads(read('META-INF/jarjar/metadata.json'))['jars']
                if not isinstance(bundled,list) or len(bundled)>256:raise ValueError('jar_nesting_limit')
                for nested in bundled:
                    filename=nested['path']
                    if not isinstance(filename,str) or not filename.startswith(('META-INF/jarjar/','META-INF/jars/')) or not filename.endswith('.jar') or filename not in names or names[filename].file_size>MAX_JAR:
                        raise ValueError('jar_nested_file_invalid')
                    content=archive.read(filename)
                    try:child=inspect_jar(content,_depth+1,_budget)
                    except ValueError as exc:
                        if str(exc)!='jar_mod_metadata_missing':raise
                        identity=nested['identifier'];version=nested['version']['artifactVersion']
                        if not isinstance(identity,dict) or not isinstance(version,str) or len(version)>256:raise ValueError('jar_nested_file_invalid')
                        result['embedded_libraries'].append({'group':str(identity.get('group',''))[:200],'artifact':str(identity.get('artifact',''))[:200],
                            'version':version,'sha256':hashlib.sha256(content).hexdigest()})
                    else:result['embedded'].append(child)
        else:raise ValueError('jar_mod_metadata_missing')
        if not result['mods']:raise ValueError('jar_mod_metadata_missing')
        for mod in result['mods']:
            if not re.fullmatch(r'[a-z][a-z0-9_-]{1,79}',mod['id']):raise ValueError('jar_invalid_mod_id')
            if not isinstance(mod['version'],str) or not 1<=len(mod['version'])<=256:raise ValueError('jar_invalid_mod_version')
        result['client_only_hint']=any(x['id'] in CLIENT_ONLY for x in result['mods']) or result['environment']=='client'
        if any(x['id'] in {'complementaryinstaller','iris_installer'} for x in result['mods']) and re.search(rb'^Main-Class:\s*\S+',manifest,re.M):
            result['client_installer']=True
            result['client_only_hint']=True
        result['compatibility']='unverified'
        result['sha256']=hashlib.sha256(raw).hexdigest()
        result['sha512']=hashlib.sha512(raw).hexdigest()
        return result
    except (zipfile.BadZipFile,KeyError,json.JSONDecodeError,tomllib.TOMLDecodeError,UnicodeDecodeError):
        raise ValueError('jar_invalid') from None


def prepare_jar(st,root,raw,filename):
    if not filename.casefold().endswith('.jar') or filename!=Path(filename.replace('\\','/')).name:
        raise ValueError('jar_filename_invalid')
    if not re.fullmatch(r'[A-Za-z0-9_.+() -]{1,160}\.jar',filename,re.I):raise ValueError('jar_filename_invalid')
    metadata=inspect_jar(raw);identifier=metadata['sha256']
    if metadata.get('client_installer'):raise ValueError('client_installer_not_server_mod')
    path=project_path(Path(root),'staging')/(identifier+'.jar')
    if path.exists():
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=identifier:raise ValueError('staging_integrity_failure')
    else:st.atomic(path,raw,0o440)
    return {'id':identifier,'filename':filename,'metadata':metadata,'sha256':identifier}


def stage(st,root,raw,filename,source='upload'):
    prepared=prepare_jar(st,root,raw,filename)
    identifier=prepared['id'];metadata=prepared['metadata']
    with st.change_lock(),st.db() as db:
        existing=db.execute('SELECT * FROM mods WHERE id=?',(identifier,)).fetchone()
        if existing and existing['remove_pending'] is not None:raise ValueError('mod_removal_pending')
        if not existing:
            db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,updated) VALUES(?,?,?,?,?,?,?)',
                       (identifier,filename,identifier,json.dumps(metadata),source,'staged',time.time()))
        elif existing['state'] in ['superseded','rejected']:
            # A new delivery of previously removed bytes has a new input source
            # and active intent. Do not keep an obsolete upload/provider source
            # that makes the explicitly approved drop-folder workflow ignore it.
            db.execute("UPDATE mods SET state='staged',filename=?,source=?,enabled=1,installed_enabled=0,replaces=NULL,error=NULL,remove_pending=NULL,updated=? WHERE id=?",(filename,source,time.time(),identifier))
    return {'id':identifier,'filename':filename,'metadata':metadata,'state':existing['state'] if existing and existing['state'] not in ['rejected','superseded'] else 'staged'}


def fingerprint(st):
    with st.db() as db:
        records=[dict(x) for x in db.execute("SELECT id,sha256,metadata,state,enabled,installed_enabled,replaces,origin,remove_pending FROM mods WHERE state NOT IN ('superseded','rejected') ORDER BY id")]
    value={'server':st.get('server'),'mods':records,'packs':st.get('pack_pending') or [],'world_imports':st.get('world_imports') or [],
           'guard_catalog':st.get('guard_catalog') or {}}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def scan_drop_folder(st,root):
    folder=project_path(Path(root),'mods')
    imported=st.get('manual_imports') or {};changed=False
    for path in sorted(folder.glob('*.jar'))[:1000]:
        if path.is_symlink():
            if st.rate('manual-symlink:'+path.name,1,300):st.event('mods','manual_file_rejected',data={'filename':path.name,'reason':'symlink'})
            continue
        # O_NOFOLLOW is effective in the production Linux container.
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        try:
            with os.fdopen(fd,'rb') as source:
                observed=os.fstat(source.fileno());signature=[observed.st_dev,observed.st_ino,observed.st_size,observed.st_mtime_ns]
                if imported.get(path.name,{}).get('signature')==signature or time.time()-observed.st_mtime<2:continue
                raw=source.read(MAX_JAR+1);after=os.fstat(source.fileno())
                if signature!=[after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns]:continue
            result=stage(st,root,raw,path.name,'manual')
            # Keep the user's input intact. Only the immutable staged copy is installed.
            st.event('mods','manual_file_staged',data={'id':result['id'],'filename':path.name})
            approval=st.get('folder_mod_approval') if st.get('maintenance').get('folder_automatic') else None
            imported[path.name]={'signature':signature,'sha256':result['id'],'approval':approval};changed=True
        except ValueError as exc:
            if st.rate('manual-rejected:'+path.name,1,300):st.event('mods','manual_file_rejected',data={'filename':path.name,'reason':str(exc)})
    if changed:st.set('manual_imports',{name:value for name,value in imported.items() if (folder/name).exists()})


def dependency_report(records,server):
    from .loader_catalogs import mod_format
    expected_loader=mod_format(server)
    identifiers={'minecraft':server['version'],'java':str(server.get('java',25)),
                 'fabricloader' if server['loader']=='FABRIC' else expected_loader.lower():server.get('loader_version','unknown')}
    builtins=server.get('loader_components') or {}
    if server['loader']=='FABRIC' and builtins.get('loader_version')==server.get('loader_version') and re.fullmatch('[0-9a-f]{64}',builtins.get('sha256','')):
        identifiers.update({key:value for key,value in builtins.get('components',{}).items() if key!='fabricloader'})
    issues=[];components=[];range_unknown=False;resolution_notes=[]
    def collect(meta,identifier,depth=0):
        if meta.get('environment')=='client':return
        components.append((identifier,meta,depth))
        for child in meta.get('embedded',[]):collect(child,identifier,depth+1)
    for record in records:
        meta=json.loads(record['metadata']) if isinstance(record['metadata'],str) else record['metadata']
        if meta.get('client_installer'):issues.append({'id':record['id'],'issue':'client_installer_not_server_mod'})
        if meta['loader']!=expected_loader:issues.append({'id':record['id'],'issue':'loader_mismatch'})
        if meta['client_only_hint']:issues.append({'id':record['id'],'issue':'client_only_hint'})
        collect(meta,record['id'])
    selected=components
    if server['loader']=='FABRIC':
        roots=[x for x in components if x[2]==0];nested={}
        fixed=set(identifiers)
        for _,meta,_ in roots:fixed.update(x['id'] for x in meta['mods']);fixed.update(meta.get('provides',[]))
        for entry in components:
            if entry[2] and entry[1]['mods'][0]['id'] not in fixed:nested.setdefault(entry[1]['mods'][0]['id'],[]).append(entry)
        def newest(candidates):
            try:return max(candidates,key=lambda x:Version(x[1]['mods'][0]['version']))
            except ValueError:
                if len({x[1]['mods'][0]['version'] for x in candidates})>1:raise
                return candidates[0]
        try:
            choices={identifier:newest(values) for identifier,values in nested.items()}
            for _ in range(16):
                active=roots+list(choices.values());requirements={}
                for _,meta,_ in active:
                    for dependency in meta['dependencies']:
                        if dependency.get('mandatory') and dependency.get('side')!='CLIENT':requirements.setdefault(dependency['id'],[]).append(dependency['range'])
                revised={}
                for identifier,values in nested.items():
                    compatible=[]
                    for entry in values:
                        meta=entry[1];version=meta['mods'][0]['version'];provided=[identifier,*meta.get('provides',[])]
                        checks=[matches(version,predicate) for key in provided for predicate in requirements.get(key,[])]
                        if all(answer is True for answer in checks):compatible.append(entry)
                    if not compatible:raise ValueError('nested_constraints_unresolved')
                    revised[identifier]=newest(compatible)
                if all(revised[key][1].get('sha256')==choices[key][1].get('sha256') for key in revised):
                    choices=revised;break
                choices=revised
            else:raise ValueError('nested_resolution_unstable')
            selected=roots+list(choices.values())
            for identifier,values in nested.items():
                if len(values)>1:resolution_notes.append({'id':identifier,'candidate_versions':sorted({x[1]['mods'][0]['version'] for x in values}),
                    'preflight_version':choices[identifier][1]['mods'][0]['version'],'native_loader_test_required':True})
        except ValueError:
            issues.append({'id':'nested_libraries','issue':'nested_dependency_resolution_unverified'});range_unknown=True
            selected=roots
    if server['loader']=='NEOFORGE':
        # Jar-in-Jar may supply the same library through multiple parent mods.
        # Only byte-identical nested artifacts with identical inspected metadata
        # are one candidate. Root mods and different bytes remain conflicts.
        unique=[];nested_seen={}
        for entry in selected:
            identifier,meta,depth=entry
            digest=meta.get('sha256','')
            signature=json.dumps(meta,sort_keys=True,separators=(',',':'))
            if depth and re.fullmatch('[0-9a-f]{64}',digest):
                if nested_seen.get(digest)==signature:
                    resolution_notes.append({'id':meta['mods'][0]['id'],'preflight_version':meta['mods'][0]['version'],
                        'identical_nested_sha256':digest,'native_loader_test_required':True})
                    continue
                nested_seen[digest]=signature
            unique.append(entry)
        selected=unique
    for identifier,meta,_ in selected:
        provided=meta['mods']+[{'id':alias,'version':meta['mods'][0]['version']} for alias in meta.get('provides',[])]
        for mod in provided:
            if mod['id'] in identifiers:issues.append({'id':identifier,'issue':'duplicate_mod_id','dependency':mod['id']})
            identifiers[mod['id']]=mod['version']
    for identifier,meta,_ in selected:
        for dep in meta['dependencies']:
            if dep.get('side')=='CLIENT':continue
            if dep.get('kind')=='discouraged':continue
            if dep.get('kind')=='incompatible':
                if dep['id'] in identifiers:
                    matched=maven_matches(identifiers[dep['id']],dep['range'])
                    if matched is not False:issues.append({'id':identifier,'issue':'conflicting_mod' if matched else 'conflict_predicate_unverified','dependency':dep['id']})
                continue
            if not dep.get('mandatory') and not (meta['loader']!='FABRIC' and dep['id'] in identifiers):continue
            if dep['id'] not in identifiers:
                issues.append({'id':identifier,'issue':'missing_dependency','dependency':dep['id']});continue
            matched=(matches if meta['loader']=='FABRIC' else maven_matches)(identifiers[dep['id']],dep['range'])
            if matched is not True:
                issues.append({'id':identifier,'issue':'version_mismatch' if matched is False else 'version_predicate_unverified',
                               'dependency':dep['id'],'actual':identifiers[dep['id']],'required':dep['range']})
                range_unknown=range_unknown or matched is None
        for conflict in meta.get('breaks',[]):
            if conflict['id'] not in identifiers:continue
            matched=matches(identifiers[conflict['id']],conflict['range'])
            if matched is not False:issues.append({'id':identifier,'issue':'conflicting_mod' if matched else 'conflict_predicate_unverified','dependency':conflict['id']})
    return {'structural_checks':'failed' if issues else 'passed','issues':issues,
            'version_range_checks':'unverified' if range_unknown else 'failed' if issues else 'passed','runtime_compatibility':'unverified',
            'nested_resolution':resolution_notes,'native_loader_is_authoritative':True}


def trial_report(st):
    """Expose only the bounded, non-secret fields from retained operator test evidence."""
    path=st.state/'requested-mod-test-results.json'
    if not path.exists():return None
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        with os.fdopen(fd,'rb') as stream:
            raw=stream.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('mod_test_report_invalid')
        document=json.loads(raw)
        basis=document['basis'];rows=[]
        for row in document['results']:
            from .sources import reference
            reference(row['source_url'])
            if row['status'] not in ['isolated_start_passed','isolated_start_failed','blocked_by_dependencies','not_applicable_to_fixed_basis','blocked_during_download_or_dependencies','client_only_declared']:
                raise ValueError('mod_test_report_invalid')
            rows.append({key:row.get(key) for key in ['name','source_url','status','versions','prerelease','provider_file_id','sha256']})
        if len(rows)>100 or not isinstance(document['checked_at'],(int,float)):raise ValueError('mod_test_report_invalid')
        from .runtime_state import compare
        return {'checked_at':document['checked_at'],'basis':{key:basis[key] for key in ['version','java','loader','loader_version']},
            'basis_matches_configuration':compare(st.get('server'),basis)['state']=='consistent','results':rows,
            'combined_start_passed':(document.get('combined') or {}).get('state')=='isolated_start_passed',
            'client_interactions_tested':False,'visitor_permissions_with_extra_mods_tested':False,
            'installation_approved':False}
    except (KeyError,TypeError,json.JSONDecodeError):raise ValueError('mod_test_report_invalid')


def check_modrinth(st):
    server=st.get('server')
    with st.db() as db:records=[dict(x) for x in db.execute("SELECT * FROM mods WHERE state NOT IN ('superseded','rejected') AND source!='curseforge'")]
    with httpx.Client(base_url='https://api.modrinth.com/v2',timeout=15,follow_redirects=False,
                      headers={'User-Agent':AGENT}) as client:
        for record in records:
            meta=json.loads(record['metadata'])
            if any(x['id']=='mcj_guard' for x in meta['mods']):
                with st.db() as db:db.execute('UPDATE mods SET available=? WHERE id=?',(json.dumps({'status':'system_managed','version':meta['mods'][0]['version']}),record['id']))
                continue
            origin=json.loads(record['origin']) if record.get('origin') else {}
            if origin.get('provider')=='manual_patch':
                with st.db() as db:db.execute('UPDATE mods SET available=?,updated=? WHERE id=?',
                    (json.dumps({'status':'locally_patched','version':meta['mods'][0]['version']}),time.time(),record['id']))
                continue
            if origin.get('pinned') and not origin.get('pack_project'):
                with st.db() as db:db.execute('UPDATE mods SET available=?,updated=? WHERE id=?',(json.dumps({'status':'pinned','version':None}),time.time(),record['id']))
                continue
            try:
                response=client.get('/version_file/'+meta['sha512'],params={'algorithm':'sha512'})
                if response.status_code==404:result={'status':'unknown_source','version':None}
                else:
                    response.raise_for_status();installed=response.json();project=installed['project_id']
                    response=client.get('/project/'+project+'/version',params={'loaders':json.dumps([provider_loader(server)]),'game_versions':json.dumps([server['version']])})
                    response.raise_for_status()
                    versions=[x for x in response.json() if x['version_type']=='release']
                    versions.sort(key=lambda x:x['date_published'],reverse=True)
                    if not versions:result={'status':'no_stable_compatible_version','version':None}
                    else:
                        version=versions[0]
                        same=any(x.get('hashes',{}).get('sha512')==meta['sha512'] for x in version['files'])
                        result={'status':'current' if same else 'available','version':version['version_number'],
                                'modrinth_version_id':version['id'],'project_id':project}
                with st.db() as db:db.execute('UPDATE mods SET available=?,updated=? WHERE id=?',(json.dumps(result),time.time(),record['id']))
            except Exception as exc:
                with st.db() as db:db.execute('UPDATE mods SET available=?,updated=? WHERE id=?',
                    (json.dumps({'status':'check_failed','error_class':type(exc).__name__}),time.time(),record['id']))


def is_client_installer(row):
    metadata=row.get('metadata') or {}
    if isinstance(metadata,str):metadata=json.loads(metadata)
    return bool(metadata.get('client_installer'))


def quarantine_client_installers(db):
    """Keep rejected upload evidence visible without treating it as installed."""
    quarantined=[]
    for row in db.execute('SELECT id,metadata FROM mods').fetchall():
        if is_client_installer(dict(row)):
            db.execute("UPDATE mods SET state='failed',enabled=0,installed_enabled=0,available=NULL,error='client_installer_not_server_mod',updated=? WHERE id=?",(time.time(),row['id']))
            quarantined.append(row['id'])
    return quarantined


def proposed_records(records):
    records=[row for row in records if row['state'] not in ['superseded','rejected'] and not is_client_installer(row)]
    replaced={row.get('replaces') for row in records if row['state']=='staged' and row.get('replaces')}
    return [row for row in records if row['id'] not in replaced]


def selected_records(records, selection):
    """Apply one verified install selection, retaining other pending mod changes."""
    if not isinstance(selection,list) or not 1<=len(selection)<=100 or len(set(selection))!=len(selection) or any(not isinstance(x,str) or not re.fullmatch('[0-9a-f]{64}',x) for x in selection):
        raise ValueError('mod_plan_stale')
    available={row['id']:row for row in records if row['state'] not in ['superseded','rejected']}
    if not set(selection).issubset(available):raise ValueError('mod_plan_stale')
    if any(is_client_installer(available[x]) for x in selection):raise ValueError('client_installer_not_server_mod')
    available={key:row for key,row in available.items() if not is_client_installer(row)}
    included=set(selection)
    for identifier in selection:
        previous=available[identifier].get('replaces');seen={identifier}
        while previous:
            if previous in seen:raise ValueError('mod_replacement_cycle')
            seen.add(previous)
            if previous not in available:break
            included.add(previous);previous=available[previous].get('replaces')
    return [{**row,'enabled':row['installed_enabled']} if row['state']=='installed' else dict(row)
            for row in records if not is_client_installer(row) and (row['state']=='installed' or row['id'] in included)]


def download_modrinth(client,file):
    parsed=urlparse(file.get('url',''))
    if parsed.scheme!='https' or parsed.netloc!='cdn.modrinth.com' or not parsed.path.startswith('/data/') or parsed.query or parsed.fragment:
        raise ValueError('mod_download_source_invalid')
    expected=file.get('hashes',{}).get('sha512','')
    if not re.fullmatch('[0-9a-f]{128}',expected):raise ValueError('mod_download_hash_missing')
    size=file.get('size')
    if type(size) is not int or not 0<size<=MAX_JAR:raise ValueError('jar_too_large')
    raw=bytearray()
    with client.stream('GET',file['url']) as response:
        response.raise_for_status()
        for part in response.iter_bytes(65536):
            raw.extend(part)
            if len(raw)>MAX_JAR or len(raw)>size:raise ValueError('jar_too_large')
    if len(raw)!=size or hashlib.sha512(raw).hexdigest()!=expected:raise ValueError('mod_download_hash_mismatch')
    return bytes(raw)


def stage_modrinth_update(st,root,identifier):
    with st.db() as db:
        found=db.execute('SELECT * FROM mods WHERE id=?',(identifier,)).fetchone()
    if not found:raise ValueError('mod_unavailable')
    record=dict(found)
    if record.get('remove_pending') is not None:raise ValueError('mod_removal_pending')
    if record['state'] in ['superseded','rejected']:raise ValueError('mod_unavailable')
    if record['source']=='system':raise ValueError('visitor_guard_is_protected')
    available=json.loads(record['available']) if record['available'] else {}
    if available.get('status')!='available':raise ValueError('mod_update_unavailable')
    version_id=available.get('modrinth_version_id','')
    if not re.fullmatch('[A-Za-z0-9]{1,40}',version_id):raise ValueError('mod_update_unavailable')
    server=st.get('server')
    with httpx.Client(base_url='https://api.modrinth.com/v2',timeout=30,follow_redirects=False,
                      headers={'User-Agent':AGENT}) as client:
        response=client.get('/version/'+version_id);response.raise_for_status();version=response.json()
        if version['project_id']!=available.get('project_id') or version['version_type']!='release' or server['version'] not in version['game_versions'] or provider_loader(server) not in version['loaders']:
            raise ValueError('candidate_mod_dependencies_failed')
        files=[x for x in version['files'] if x.get('primary') and x['filename'].lower().endswith('.jar')]
        if len(files)!=1:raise ValueError('mod_primary_file_unverified')
        file=files[0];raw=download_modrinth(client,file)
    meta=inspect_jar(raw);old=json.loads(record['metadata'])
    if {x['id'] for x in meta['mods']}!={x['id'] for x in old['mods']}:raise ValueError('mod_identity_changed')
    staged=stage(st,root,raw,file['filename'],'modrinth')
    if staged['id']==identifier:raise ValueError('mod_update_unavailable')
    with st.db(immediate=True) as db:
        # Preserve the user's desired enabled state; never replace the active JAR here.
        db.execute('UPDATE mods SET replaces=?,enabled=?,updated=? WHERE id=?',(identifier,record['enabled'],time.time(),staged['id']))
    st.event('mods','mod_update_staged',data={'id':staged['id'],'replaces':identifier,'version':version['version_number']})
    return {**staged,'replaces':identifier,'enabled':bool(record['enabled']),'installed':False}

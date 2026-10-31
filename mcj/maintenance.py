"""Backup, isolated validation and atomic promotion for approved management jobs."""
from .project_paths import project_path
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import time
from .store import Store
from . import mods,versions,storage_preflight
from .job_control import phase
from .server_settings import SECRET_KEYS
from . import properties as java_properties
from .runtime_state import compare as compare_runtime

def store(c):return Store(project_path(c.ROOT,'state'),project_path(c.ROOT,'secrets/encryption'))

def restore_runtime(saved,target):
    # The startup script is deliberately read-only. Replace directory entries
    # atomically instead of opening a protected existing script for writing.
    for path in Path(saved).iterdir():
        if path.is_symlink() or not path.is_file():raise RuntimeError('unsafe_rollback_runtime')
        Store.atomic(Path(target)/path.name,path.read_bytes(),stat.S_IMODE(path.stat().st_mode))

def require_runtime_consistency(c,st):
    observed=json.loads((project_path(c.ROOT,'control/runtime/runtime.json')).read_text())
    if compare_runtime(st.get('server'),observed)['state']!='consistent':raise ValueError('runtime_configuration_mismatch')

def full_backup(c,kind,actor=None,resume=True):
    operation={'pre_version_test':'version_test','pre_version':'version_apply','pre_mods':'apply_mods','pre_combined':'apply_mods','pre_settings':'server_settings','pre_world':'world_change','pre_world_export':'world_export','pre_world_delete':'world_delete'}.get(kind)
    if operation:storage_preflight.require(c.ROOT,c.BACKUPS,operation)
    phase('backup');st=store(c);identifier=secrets.token_hex(16)
    with st.db() as db:db.execute('INSERT INTO backups(id,created,kind,state) VALUES(?,?,?,?)',(identifier,time.time(),kind,'running'))
    try:
        result=c.archive_backup(kind,resume=resume)
        with st.db() as db:db.execute('UPDATE backups SET state=?,path=?,size=?,sha256=?,verified=? WHERE id=?',
            ('verified',result['path'],result['size'],result['sha256'],result['verified'],identifier))
        st.event('backup','backup_verified',actor,{'id':identifier,'kind':kind,'size':result['size']})
        return {**result,'manager_backup_id':identifier}
    except Exception as exc:
        with st.db() as db:db.execute('UPDATE backups SET state=?,error=? WHERE id=?',('failed',type(exc).__name__,identifier))
        st.event('backup','backup_failed',actor,{'id':identifier,'kind':kind});raise

def image_for(c,java,pull=False):
    channel=versions.JAVA_CHANNELS.get(java)
    if not channel:raise ValueError('unsupported_java_channel')
    reference='itzg/minecraft-server:'+channel
    image=c.client.images.pull('itzg/minecraft-server',tag=channel) if pull else c.client.images.get(reference)
    digests=[x.split('@',1)[1] for x in image.attrs.get('RepoDigests',[]) if x.startswith('itzg/minecraft-server@')]
    if len(set(digests))!=1:raise RuntimeError('game_image_digest_unverified')
    return image.id,reference+'@'+digests[0]

def safe_remove(c,path):
    path=Path(path)
    if path.is_symlink() or path.resolve().parent!=(project_path(c.ROOT,'.restore-tests')).resolve():raise RuntimeError('unsafe_candidate_cleanup')
    shutil.rmtree(path)

def staged_bytes(c,row):
    if not re.fullmatch('[0-9a-f]{64}',row['id']) or row['sha256']!=row['id']:raise RuntimeError('staging_identity_invalid')
    path=project_path(c.ROOT,'staging')/(row['id']+'.jar')
    if path.is_symlink() or not path.is_file() or path.stat().st_size>mods.MAX_JAR:raise RuntimeError('staging_file_unavailable')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise RuntimeError('staging_integrity_failure')
    return raw

def require_candidate_admission(c,built):
    from .player_admission import require_target,whitelist_value
    runtime=built['runtime'];trusted=c.trusted_guard(runtime['version'],runtime['loader'])
    if built['guard'].get('sha256')!=trusted['sha256']:raise ValueError('guard_artifact_integrity_failed')
    path=Path(built['data'])/'server.properties'
    if path.is_symlink() or not path.is_file():raise ValueError('invalid_server_property')
    effective=java_properties.loads(path.read_text(encoding='utf-8'))
    actual=require_target(effective,trusted,runtime)
    if actual!=whitelist_value(runtime.get('properties',{}).get('white-list')):
        raise ValueError('runtime_configuration_mismatch')

def prepare_dependencies(c,scratch,data,runtime,image):
    """The trusted image prepares core files with SETUP_ONLY; staged mods are absent."""
    hidden=scratch/'mods-during-setup'
    if (data/'mods').exists():os.rename(data/'mods',hidden)
    (data/'mods').mkdir(mode=0o750)
    network=None;container=None
    try:
        network=c.client.networks.create('mcj_setup_'+secrets.token_hex(6),labels={'mcj.purpose':'runtime-setup','mcj.project':c.PROJECT})
        host_root=Path(os.environ.get('HOST_PROJECT_ROOT','/volume1/docker/minecraftjava'))
        data_host=str(host_root/data.relative_to(c.ROOT))
        environment={'EULA':'TRUE','TYPE':runtime['loader'],'VERSION':runtime['version'],'UID':str(os.getuid()),'GID':str(os.getgid()),
          'MEMORY':'3072M','SETUP_ONLY':'true','SKIP_SERVER_PROPERTIES':'true','OVERRIDE_SERVER_PROPERTIES':'false',
          'FABRIC_LOADER_VERSION':runtime.get('loader_version',''),'FABRIC_INSTALLER_VERSION':runtime.get('installer_version','1.1.2'),
          'FORGE_VERSION':runtime.get('loader_version',''),'NEOFORGE_VERSION':runtime.get('loader_version',''),'DEBUG':'false'}
        container=c.client.containers.run(image,detach=True,network=network.name,user=__import__('mcj.service_identity',fromlist=['user']).user(),
          environment=environment,volumes={data_host:{'bind':'/data','mode':'rw'}},mem_limit='3g',nano_cpus=2_000_000_000,
          pids_limit=256,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
          labels={'mcj.purpose':'runtime-setup','mcj.project':c.PROJECT})
        outcome=container.wait(timeout=300)
        if outcome.get('StatusCode')!=0:raise RuntimeError('runtime_dependency_setup_failed')
    finally:
        if container:
            container.reload()
            if container.status=='running':container.stop(timeout=20)
            container.remove(v=True)
        if network:network.remove()
        if (data/'mods').exists():shutil.rmtree(data/'mods')
        if hidden.exists():os.rename(hidden,data/'mods')

def candidate(c,backup,configuration,image,records=None,restore=False,include_pending=True):
    phase('preparing');scratch,data,metadata,metadata_path=c.extract_archive(backup['path'])
    try:
        old_runtime=json.loads((scratch/'runtime.json').read_text())
        runtime=versions.ensure_runtime_components(store(c),{**old_runtime,**configuration})
        guard=c.trusted_guard(runtime['version'],runtime['loader'])
        if restore:
            actual=[]
            mapping_path=scratch/'mod-manifest.json'
            mapping={x['sha256']:x for x in json.loads(mapping_path.read_text())} if mapping_path.exists() else {}
            protected={x['sha256'] for x in [guard,*guard.get('dependencies',[])]}
            for directory,enabled in [('mods',1),('mods-disabled',0)]:
                for path in (data/directory).glob('*.jar'):
                    raw=path.read_bytes();meta=mods.inspect_jar(raw);original=mapping.get(meta['sha256'],{})
                    if mods.is_client_installer({'metadata':meta}):
                        if enabled:raise ValueError('client_installer_not_server_mod')
                        path.unlink()  # Extracted candidate only; the original backup remains intact.
                        continue
                    filename=original.get('filename',path.name)
                    if filename!=Path(filename).name:raise RuntimeError('backup_mod_filename_invalid')
                    source=original.get('source','restored')
                    if source not in ['upload','manual','curseforge','modrinth','pack','restored']:source='restored'
                    actual.append({'id':meta['sha256'],'filename':filename,'sha256':meta['sha256'],'metadata':meta,'enabled':enabled,
                        'source':'system' if meta['sha256'] in protected else source,'origin':original.get('origin')})
        else:
            st=store(c)
            if records is None:
                with st.db() as db:records=[dict(x) for x in db.execute("SELECT * FROM mods WHERE state!='superseded'")]
            if include_pending:records=[row for row in records if row.get('remove_pending') is None]
            records=mods.proposed_records(records)
            actual=[]
            for path in [data/'mods',data/'mods-disabled']:
                if path.is_symlink():raise RuntimeError('unsafe_mod_directory')
                if path.exists():shutil.rmtree(path)
                path.mkdir(mode=0o750)
            filenames=set()
            for row in records:
                if row['source']=='system':continue
                filename=row['filename']
                if filename!=Path(filename).name or not re.fullmatch(r'[A-Za-z0-9_.+() -]{1,160}\.jar',filename,re.I):raise ValueError('jar_filename_invalid')
                raw=staged_bytes(c,row);meta=mods.inspect_jar(raw)
                if mods.is_client_installer({'metadata':meta}):raise ValueError('client_installer_not_server_mod')
                if any(x['id']=='mcj_guard' for x in meta['mods']):raise ValueError('visitor_guard_is_protected')
                if row['enabled'] and filename in filenames:raise ValueError('duplicate_mod_filename')
                if row['enabled']:filenames.add(filename)
                destination=data/('mods' if row['enabled'] else 'mods-disabled')/(filename if row['enabled'] else row['id']+'.jar')
                Store.atomic(destination,raw,0o440)
                actual.append({**row,'metadata':meta})
            for artifact in [guard,*guard.get('dependencies',[])]:
                source=project_path(c.ROOT,artifact['path']);raw=source.read_bytes();meta=mods.inspect_jar(raw)
                Store.atomic(data/'mods'/artifact['filename'],raw,0o440)
                actual.append({'id':meta['sha256'],'filename':artifact['filename'],'sha256':meta['sha256'],'metadata':meta,'enabled':1,'source':'system'})
        from . import packs,worlds
        if not restore:worlds.apply_import(store(c),c.ROOT,data,runtime)
        if old_runtime.get('version')!=runtime.get('version') or guard.get('minecraft_data_version'):
            worlds.require_supported_format(data,runtime,guard)
        if restore:
            pack_installations=packs.restored_state(scratch/'pack-state.json')
        elif include_pending:pack_installations=packs.apply_pending(store(c),c.ROOT,data,runtime)
        else:pack_installations=store(c).get('pack_installations') or {}
        phase('checking_mods');report=mods.dependency_report([x for x in actual if x['enabled']],runtime)
        if report['structural_checks']!='passed' or report['version_range_checks']!='passed':
            from .job_control import dependency_failure
            dependency_failure(report,actual)
            raise ValueError('candidate_mod_dependencies_failed')
        properties=java_properties.loads((data/'server.properties').read_text(encoding='utf-8'))
        for key,value in runtime.get('properties',{}).items():
            if not isinstance(key,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,80}',key) or not isinstance(value,(str,int,bool)):raise ValueError('invalid_server_property')
            text=str(value).lower() if isinstance(value,bool) else str(value)
            if len(text)>4000 or any(x in text for x in ['\r','\n','\x00']):raise ValueError('invalid_server_property')
            if key=='rcon.password':continue
            properties[key]=text
        properties.update({'online-mode':'true','gamemode':'spectator','force-gamemode':'true','rcon.password':c.RCON,'enable-rcon':'true','rcon.port':'25575','server-port':'25565','enable-query':'false'})
        if runtime['version'].startswith('26.'):properties['pause-when-empty-seconds']='0'
        from .player_admission import require_target
        properties['white-list']=require_target(properties,guard,runtime)
        Store.atomic(data/'server.properties',java_properties.dumps(properties).encode('utf-8'))
        runtime['properties']={k:v for k,v in properties.items() if k not in SECRET_KEYS}
        Store.atomic(scratch/'runtime.json',json.dumps(runtime).encode(),0o640)
        Store.atomic(scratch/'guard.json',json.dumps(guard).encode(),0o640)
        if any(old_runtime.get(k)!=runtime.get(k) for k in ['version','loader','loader_version','installer_version']):
            prepare_dependencies(c,scratch,data,runtime,image)
        if runtime['loader']=='FABRIC' and runtime.get('loader_components'):
            proof=runtime['loader_components'];version=runtime['loader_version']
            loader=data/'libraries/net/fabricmc/fabric-loader'/version/('fabric-loader-'+version+'.jar')
            if loader.is_symlink() or not loader.is_file() or hashlib.sha256(loader.read_bytes()).hexdigest()!=proof['sha256']:
                raise ValueError('loader_runtime_hash_mismatch')
        if runtime['loader']=='NEOFORGE':
            proof=runtime.get('loader_components') or {};version=runtime['loader_version']
            loader=data/'libraries/net/neoforged/neoforge'/version/('neoforge-'+version+'-universal.jar')
            if proof.get('loader')!='NEOFORGE' or proof.get('loader_version')!=version or loader.is_symlink() or not loader.is_file() or hashlib.sha256(loader.read_bytes()).hexdigest()!=proof.get('sha256'):
                raise ValueError('loader_runtime_hash_mismatch')
        phase('test_starting');tested=c.isolated_data_test(scratch,data,runtime,guard,image,'candidate',keep_data=True)
        built={'scratch':scratch,'data':data,'runtime':runtime,'guard':guard,'mods':actual,'test':tested,'dependencies':report,'pack_installations':pack_installations}
        require_candidate_admission(c,built)
        return built
    except Exception:
        if scratch.exists():safe_remove(c,scratch)
        raise

def idle_gate(c):
    container=c.target();running=container.status=='running'
    c.gate(True)
    if running:
        time.sleep(2)
        count=c.player_count()
        if count is None:c.gate(False);raise RuntimeError('player_count_unknown')
        from .job_control import may_disconnect_players
        if count!=0 and not may_disconnect_players():c.gate(False);raise RuntimeError('players_online')
    return container,running

def plan(c,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('invalid_version_plan')
    st=store(c)
    with st.db() as db:row=db.execute('SELECT * FROM version_plans WHERE id=?',(identifier,)).fetchone()
    if not row:raise ValueError('version_plan_not_found')
    value=dict(row)
    value['configuration']=json.loads(value['configuration']);value['report']=json.loads(value['report'])
    if value['based_on']!=json.dumps(st.get('server'),sort_keys=True):raise ValueError('version_plan_stale')
    if value.get('mod_fingerprint')!=mods.fingerprint(st):raise ValueError('mod_plan_stale')
    if value['report']['metadata_checks']!='passed':raise ValueError('version_plan_blocked')
    return st,value

def test_version(c,identifier,actor):
    st,value=plan(c,identifier)
    if value['state']=='tested' and value.get('test_result'):return json.loads(value['test_result'])
    require_runtime_consistency(c,st)
    storage_preflight.require(c.ROOT,c.BACKUPS,'version_test')
    container,running=idle_gate(c)
    built=None
    try:
        backup=full_backup(c,'pre_version_test',actor,resume=True)
        image,reference=image_for(c,value['configuration']['java'],pull=True)
        built=candidate(c,backup,{**st.get('server'),**value['configuration']},image)
        report={**built['test'],'metadata_checks':'passed','backup_id':backup['manager_backup_id'],'image_reference':reference,'live_configuration_changed':False}
        with st.db() as db:db.execute('UPDATE version_plans SET state=?,test_result=?,backup_id=?,image_id=?,updated=? WHERE id=?',
            ('tested',json.dumps(report),backup['manager_backup_id'],reference,time.time(),identifier))
        st.event('maintenance','version_test_passed',actor,{'id':identifier,'version':value['configuration']['version']})
        return report
    except Exception as exc:
        with st.db() as db:db.execute('UPDATE version_plans SET state=?,test_result=?,updated=? WHERE id=?',('failed',json.dumps({'error_class':type(exc).__name__,'reason':str(exc)[:150] if isinstance(exc,(RuntimeError,ValueError)) else 'operation_failed','live_configuration_changed':False}),time.time(),identifier))
        st.event('maintenance','version_test_failed',actor,{'id':identifier});raise
    finally:
        if built and built['scratch'].exists():safe_remove(c,built['scratch'])
        c.gate(False if running else True)

def promote(c,built,image_reference,backup,actor,kind):
    if any(mods.is_client_installer(row) for row in built['mods']):raise ValueError('client_installer_not_server_mod')
    require_candidate_admission(c,built)
    st=store(c);root=c.ROOT;container=c.target();old_image=container.attrs['Image']
    identifier=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+secrets.token_hex(4)
    rollback=project_path(root,'.rollback')/identifier;rollback.mkdir(parents=True,mode=0o700)
    shutil.copytree(project_path(root,'control/runtime'),rollback/'runtime')
    env=Path(os.environ.get('HOST_PROJECT_ROOT','/volume1/docker/minecraftjava'))/'.env'
    old_env=env.read_bytes() if env.exists() else None
    old_settings=st.get('server')
    old_packs={'pack_installations':st.get('pack_installations') or {},'pack_pending':st.get('pack_pending') or []}
    with st.db() as db:old_mods=[dict(x) for x in db.execute('SELECT * FROM mods')]
    journal={'id':identifier,'kind':kind,'backup_id':backup['manager_backup_id'],'old_image':old_image,'new_image':image_reference,'state':'prepared','at':time.time()}
    Store.atomic(rollback/'journal.json',json.dumps(journal).encode())
    c.graceful_stop(container)
    os.rename(project_path(root,'server'),rollback/'server')
    try:
        os.rename(built['data'],project_path(root,'server'))
        Store.atomic(project_path(root,'control/runtime/runtime.json'),json.dumps(built['runtime']).encode(),0o640)
        Store.atomic(project_path(root,'control/runtime/start.sh'),(Path(__file__).parent.parent/'start-game.sh').read_bytes(),0o550)
        Store.atomic(project_path(root,'control/runtime/guard.json'),json.dumps(built['guard']).encode(),0o640)
        Store.atomic(project_path(root,'control/runtime/guard.sha256'),(built['guard']['sha256']+'  '+built['guard']['filename']+'\n').encode(),0o640)
        c.guard_integrity();c.deploy_game(image_reference);c.wait_health()
        st.set('server',built['runtime'])
        st.set('pack_installations',built.get('pack_installations',{}))
        if kind not in ['settings','world'] and not built.get('preserve_pending'):st.set('pack_pending',[])
        with st.db() as db:
            quarantined=set(mods.quarantine_client_installers(db))
            wanted={x['id'] for x in built['mods']}
            removed=[]
            for row in db.execute('SELECT id,state,remove_pending FROM mods').fetchall():
                if row['id'] in quarantined and row['remove_pending'] is None:continue
                if row['id'] not in wanted and (kind not in ['settings','world'] and not built.get('preserve_pending') or row['state']=='installed' or row['id'] in built.get('supersede_pending',[])):
                    if row['remove_pending'] is not None:removed.append(row['id'])
                    db.execute("UPDATE mods SET state='superseded',installed_enabled=0,remove_pending=NULL,updated=? WHERE id=?",(time.time(),row['id']))
            for row in built['mods']:
                metadata=row['metadata'];metadata=json.loads(metadata) if isinstance(metadata,str) else metadata
                raw=(project_path(root,'server')/('mods' if row['enabled'] else 'mods-disabled')/(row['filename'] if row['enabled'] else row['id']+'.jar')).read_bytes()
                st.atomic(project_path(root,'staging')/(row['id']+'.jar'),raw,0o440)
                origin=row.get('origin');origin=origin if isinstance(origin,str) else json.dumps(origin) if origin else None
                db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,enabled,installed_enabled,updated,origin) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,source=excluded.source,origin=excluded.origin,state=excluded.state,enabled=excluded.enabled,installed_enabled=excluded.installed_enabled,available=NULL,error=NULL,updated=excluded.updated',
                  (row['id'],row['filename'],row['sha256'],json.dumps(metadata),row.get('source','restored'),'installed',int(row['enabled']),int(row['enabled']),time.time(),origin))
        journal['state']='applied';Store.atomic(rollback/'journal.json',json.dumps(journal).encode())
        if removed:st.event('mods','mods_uninstalled',actor,{'ids':removed,'backup_id':backup['manager_backup_id']})
        st.event('maintenance',kind+'_applied',actor,{'rollback_id':identifier,'backup_id':backup['manager_backup_id'],'runtime':{k:built['runtime'].get(k) for k in ['version','java','loader','loader_version','world']}})
        return {'state':'applied','backup_id':backup['manager_backup_id'],'rollback_id':identifier,'runtime':built['runtime'],'isolated_test':built['test'],'installed_mods':[{'filename':row['filename'],'sha256':row['sha256']} for row in built['mods'] if row['enabled']]}
    except Exception:
        failed=c.target();failed.reload()
        if failed.status=='running':c.graceful_stop(failed)
        if (project_path(root,'server')).exists():os.rename(project_path(root,'server'),rollback/'failed-server')
        os.rename(rollback/'server',project_path(root,'server'))
        restore_runtime(rollback/'runtime',project_path(root,'control/runtime'))
        if old_env is not None:Store.atomic(env,old_env)
        elif env.exists():
            lines=[x for x in env.read_text().splitlines() if not x.startswith(('MCJ_GAME_IMAGE=','MCJ_GAME_MEMORY_MB='))]
            Store.atomic(env,('\n'.join(lines)+'\n').encode())
        c.compose_context()
        # The old immutable image remains present even when its moving tag has advanced.
        current_ref=json.loads((rollback/'journal.json').read_text())['old_image']
        old=c.client.images.get(current_ref)
        java=old_settings.get('java',25);channel=versions.JAVA_CHANNELS[java]
        digest=next(x.split('@',1)[1] for x in old.attrs['RepoDigests'] if x.startswith('itzg/minecraft-server@'))
        c.deploy_game('itzg/minecraft-server:'+channel+'@'+digest);c.wait_health();st.set('server',old_settings)
        for key,value in old_packs.items():st.set(key,value)
        with st.db() as db:
            old_ids={row['id'] for row in old_mods}
            for row in built['mods']:
                if row['id'] not in old_ids:db.execute('DELETE FROM mods WHERE id=?',(row['id'],))
            for row in old_mods:
                columns=list(row)
                db.execute('INSERT OR REPLACE INTO mods('+','.join(columns)+') VALUES('+','.join('?' for x in columns)+')',[row[x] for x in columns])
        journal['state']='rolled_back';Store.atomic(rollback/'journal.json',json.dumps(journal).encode())
        st.event('maintenance','change_rolled_back',actor,{'rollback_id':identifier,'kind':kind});raise

def apply_change(c,kind,actor,identifier=None,archive=None,configuration=None,selection=None):
    with store(c).change_lock():return _apply_change(c,kind,actor,identifier,archive,configuration,selection)


def _apply_change(c,kind,actor,identifier=None,archive=None,configuration=None,selection=None):
    st=store(c);value=None
    require_runtime_consistency(c,st)
    if kind=='version':
        st,value=plan(c,identifier)
        if value['state']!='tested' or not value.get('image_id'):raise ValueError('version_test_required')
        configuration={**st.get('server'),**value['configuration']}
        image_reference=value['image_id'];image=c.client.images.get(image_reference).id
    elif kind in ['mods','settings','world','combined']:
        if kind in ['settings','world','combined']:
            from .server_settings import normalize
            configuration=versions.ensure_runtime_components(st,normalize(st.get('server'),configuration))
        else:configuration=versions.ensure_runtime_components(st,st.get('server'))
        image=c.target().attrs['Image']
        with st.db() as db:proposed=[{**dict(x),'enabled':x['installed_enabled'] if kind in ['settings','world'] else x['enabled']} for x in db.execute("SELECT * FROM mods WHERE state='installed'" if kind in ['settings','world'] else "SELECT * FROM mods WHERE enabled=1 AND state!='superseded'")]
        if selection is not None:
            with st.db() as db:proposed=mods.selected_records([dict(x) for x in db.execute('SELECT * FROM mods')],selection)
        requirements=mods.dependency_report([row for row in mods.proposed_records(proposed) if row['enabled']],configuration)
        if requirements['structural_checks']!='passed':
            from .job_control import dependency_failure
            dependency_failure(requirements,proposed)
            raise ValueError('candidate_mod_dependencies_failed')
        current=c.client.images.get(image);channel=versions.JAVA_CHANNELS[configuration.get('java',25)]
        digest=next(x.split('@',1)[1] for x in current.attrs['RepoDigests'] if x.startswith('itzg/minecraft-server@'))
        image_reference='itzg/minecraft-server:'+channel+'@'+digest
    elif kind=='restore':
        checked,meta,_=c.checked_archive(archive)
        configuration=None;image=meta.get('docker_image_id') or c.target().attrs['Image'];image_reference=None
    else:raise ValueError('invalid_change_kind')
    if configuration and configuration.get('container_memory_mb',8192)!=st.get('server').get('container_memory_mb',8192):c.require_memory_budget(configuration)
    storage_preflight.require(c.ROOT,c.BACKUPS,{'mods':'apply_mods','combined':'apply_mods','settings':'server_settings','world':'world_change','version':'version_apply','restore':'restore'}[kind],checked if kind=='restore' else None)
    container,running=idle_gate(c);built=None
    try:
        backup=full_backup(c,'pre_'+kind,actor,resume=False)
        if kind=='restore':
            scratch,data,metadata,metadata_path=c.extract_archive(archive)
            configuration=json.loads((scratch/'runtime.json').read_text());safe_remove(c,scratch)
            built=candidate(c,{'path':archive},configuration,image,restore=True)
            old=c.client.images.get(image);channel=versions.JAVA_CHANNELS[configuration.get('java',25)]
            digest=next(x.split('@',1)[1] for x in old.attrs['RepoDigests'] if x.startswith('itzg/minecraft-server@'))
            image_reference='itzg/minecraft-server:'+channel+'@'+digest
        else:
            records=None
            if kind in ['settings','world']:
                with st.db() as db:records=[{**dict(x),'enabled':x['installed_enabled']} for x in db.execute("SELECT * FROM mods WHERE state='installed'")]
            if selection is not None:
                with st.db() as db:records=mods.selected_records([dict(x) for x in db.execute('SELECT * FROM mods')],selection)
            built=candidate(c,backup,configuration,image,records=records,include_pending=kind not in ['settings','world'] and selection is None)
            built['preserve_pending']=selection is not None
            built['supersede_pending']=[row['id'] for row in (records or []) if row['state']=='staged' and row['id'] not in (selection or [])] if selection is not None else []
        phase('promoting');result=promote(c,built,image_reference,backup,actor,kind)
        if not running:c.graceful_stop(c.target())
        if kind=='version':
            with st.db() as db:db.execute('UPDATE version_plans SET state=?,updated=? WHERE id=?',('applied',time.time(),identifier))
        return result
    except Exception:
        current=c.target();current.reload()
        if running and current.status!='running':c.guard_integrity();current.start();c.wait_health()
        raise
    finally:
        if built and built['scratch'].exists():safe_remove(c,built['scratch'])
        c.gate(False if running else True)

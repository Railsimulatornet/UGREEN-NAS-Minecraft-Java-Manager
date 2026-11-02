"""Private, authenticated controller; the web container has no Docker socket."""
from .project_paths import project_path
from contextlib import contextmanager
import hashlib
from datetime import datetime
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sqlite3
import socket
import struct
import subprocess
import tarfile
import threading
import time
import uuid
import sys
from typing import Literal
import docker
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool
from .store import Store
from .infrastructure import compose_identity,validate_game_configuration,stop_container,compose_game_reference,verify_game_reference
from . import maintenance, properties as java_properties, role_permissions
from . import client_packs, storage_preflight,game_access
from .telemetry import normalized_cpu,DockerSamples

ROOT=Path(os.environ.get('PROJECT_ROOT','/project'))
BACKUPS=Path(os.environ.get('BACKUP_ROOT','/backups'))
PROJECT=os.environ.get('PROJECT_NAME','ugreen_minecraft_java')
TOKEN=Path(os.environ.get('RPC_SECRET','/run/secrets/rpc')).read_text().strip()
RCON=Path(os.environ.get('RCON_SECRET','/run/secrets/rcon')).read_text().strip()
LOCK=threading.Lock()
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
client=docker.from_env(timeout=20)
status_samples=DockerSamples()

@app.on_event('startup')
def packaged_guard_candidates():
    from .guard_bundle import install_registry
    install_registry(ROOT)

@app.get('/healthz')
def health():return {'ok':True,'scope':'private_controller'}

@app.middleware('http')
async def authenticate(request,call_next):
    supplied=request.headers.get('Authorization','')
    if not hmac.compare_digest(supplied,'Bearer '+TOKEN):
        from starlette.responses import JSONResponse
        return JSONResponse({'detail':'unauthorized'},status_code=401)
    if int(request.headers.get('Content-Length','0'))>65536:
        from starlette.responses import JSONResponse
        return JSONResponse({'detail':'request_too_large'},status_code=413)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    return response

def target():
    matches=client.containers.list(all=True,filters={'label':[
        'com.docker.compose.project='+PROJECT,'com.docker.compose.service=minecraft']})
    if len(matches)!=1:raise RuntimeError('Minecraft service identity is ambiguous or missing')
    container=matches[0];container.reload()
    labels=container.labels
    if labels.get('com.docker.compose.project')!=PROJECT or labels.get('com.docker.compose.service')!='minecraft':
        raise RuntimeError('Minecraft service identity changed')
    return container

def compose_context():
    container=target()
    host_root=os.environ.get('HOST_PROJECT_ROOT','/volume1/docker/minecraftjava')
    prefix,service=compose_identity(container.attrs,host_root,PROJECT)
    operation=subprocess.run(prefix+['config','--format','json'],capture_output=True,text=True,timeout=30)
    if operation.returncode:raise RuntimeError('compose_configuration_failed')
    config=json.loads(operation.stdout)
    bindings=container.attrs['HostConfig'].get('PortBindings',{}).get('25565/tcp',[])
    if len(bindings)!=1:raise RuntimeError('unexpected_game_publication')
    expected_bind=os.environ.get('GAME_BIND_ADDRESS','127.0.0.1')
    if bindings[0].get('HostIp')!=expected_bind:raise RuntimeError('unexpected_game_publication')
    voice_port=os.environ.get('VOICE_CHAT_PORT') or None
    if voice_port:
        voice_port=int(voice_port)
        voice_properties=java_properties.loads((project_path(ROOT,'server/config/voicechat/voicechat-server.properties')).read_text())
        if voice_port!=24454 or voice_properties.get('port')!='24454':raise RuntimeError('unexpected_game_publication')
    validate_game_configuration(config,host_root,container.name,int(bindings[0]['HostPort']),expected_bind,voice_port)
    reference=config['services'][service]['image']
    verify_game_reference(reference,client.images.get(reference).id)
    return prefix,service,config

def deploy_game(image_reference=None):
    prefix,service,configuration=compose_context()
    from . import memory_budget
    runtime=json.loads(project_path(ROOT,'control/runtime/runtime.json').read_text())
    wanted_memory,_=memory_budget.limits(runtime)
    require_memory_budget(runtime)
    environment=Path(os.environ.get('HOST_PROJECT_ROOT','/volume1/docker/minecraftjava'))/'.env'
    if environment.is_symlink():raise ValueError('unsafe_project_environment')
    lines=environment.read_text().splitlines() if environment.exists() else []
    lines=[line for line in lines if not line.startswith('MCJ_GAME_MEMORY_MB=')]
    Store.atomic(environment,('\n'.join(lines+['MCJ_GAME_MEMORY_MB='+str(wanted_memory)])+'\n').encode(),0o600)
    _,_,configuration=compose_context()
    if int(configuration['services'][service].get('mem_limit',0))!=wanted_memory*1024**2:
        raise RuntimeError('compose_game_memory_selection_mismatch')
    if image_reference is not None:
        if not re.fullmatch(r'itzg/minecraft-server:(java17|java21|java25)@sha256:[0-9a-f]{64}',image_reference):
            raise ValueError('untrusted_game_image')
        approved=client.images.get(image_reference)
        display_reference=compose_game_reference(image_reference,approved.id)
        if not approved.tag('itzg/minecraft-server',tag=display_reference.split(':',1)[1]):raise RuntimeError('game_image_alias_failed')
        environment=Path(os.environ.get('HOST_PROJECT_ROOT','/volume1/docker/minecraftjava'))/'.env'
        if environment.is_symlink():raise ValueError('unsafe_project_environment')
        lines=environment.read_text().splitlines() if environment.exists() else []
        lines=[line for line in lines if not line.startswith('MCJ_GAME_IMAGE=')]
        Store.atomic(environment,('\n'.join(lines+['MCJ_GAME_IMAGE='+display_reference])+'\n').encode(),0o600)
        _,_,configuration=compose_context()
        if configuration['services'][service]['image']!=display_reference:
            raise RuntimeError('compose_game_image_selection_mismatch')
    expected_image=approved.id if image_reference is not None else client.images.get(configuration['services'][service]['image']).id
    operation=subprocess.run(prefix+['up','-d','--no-deps','--no-build','--pull','never',service],capture_output=True,text=True,timeout=150)
    if operation.returncode:raise RuntimeError('compose_game_deployment_failed')
    actual=target()
    if actual.attrs['Image']!=expected_image:raise RuntimeError('deployed_game_image_mismatch')
    if actual.attrs['HostConfig'].get('Memory')!=wanted_memory*1024**2:raise RuntimeError('deployed_game_memory_mismatch')
    return actual

def require_memory_budget(configuration):
    from . import memory_budget
    container=target();used=0
    if container.status=='running':used=status_samples.collect(container).get('memory_stats',{}).get('usage',0)
    result=memory_budget.forecast(configuration,memory_budget.host_memory(),used)
    current=container.attrs['HostConfig'].get('Memory',0)//1024**2
    if configuration.get('container_memory_mb',8192)>current and not result['sufficient']:raise ValueError('insufficient_host_memory')
    return result

@app.get('/memory-budget')
def memory_budget_status():
    container=target();runtime=json.loads(project_path(ROOT,'control/runtime/runtime.json').read_text())
    current=int(container.attrs['HostConfig'].get('Memory',0))//1024**2
    result=require_memory_budget({**runtime,'container_memory_mb':current})
    return {**result,'configured_container_mb':runtime.get('container_memory_mb',8192)}

def read_exact(connection,count):
    data=b''
    while len(data)<count:
        chunk=connection.recv(count-len(data))
        if not chunk:raise ConnectionError('RCON connection closed')
        data+=chunk
    return data

def receive(connection):
    length=struct.unpack('<i',read_exact(connection,4))[0]
    if length<10 or length>65536:raise RuntimeError('RCON packet limit')
    packet=read_exact(connection,length)
    identifier,kind=struct.unpack('<ii',packet[:8])
    return identifier,kind,packet[8:-2].decode('utf-8','replace')

def rcon(command):
    if not isinstance(command,str) or len(command)>2000 or any(x in command for x in ['\x00','\r','\n']):
        raise ValueError('Invalid Minecraft command')
    with socket.create_connection(('minecraft',25575),timeout=4) as connection:
        def send(identifier,kind,text):
            data=struct.pack('<ii',identifier,kind)+text.encode()+b'\0\0'
            connection.sendall(struct.pack('<i',len(data))+data)
        send(11,3,RCON)
        identifier,kind,_=receive(connection)
        if identifier==-1:raise RuntimeError('RCON authentication rejected')
        if kind!=2:
            identifier,kind,_=receive(connection)
        if identifier!=11 or kind!=2:raise RuntimeError('RCON authentication response invalid')
        # A synchronous world flush can outlast a normal RCON status query.
        if command=='save-all flush':connection.settimeout(120)
        send(12,2,command)
        identifier,kind,text=receive(connection)
        if identifier!=12:raise RuntimeError('RCON command response invalid')
        return text.replace(RCON,'[REDACTED]')

def player_count():
    try:
        text=rcon('list')
        match=re.match(r'^There are (\d+) of a max of (\d+) players online\s*:',text)
        if not match:return None
        return int(match[1])
    except Exception:return None

def guard_integrity():
    manifest=project_path(ROOT,'control/runtime/guard.json')
    if not manifest.exists():raise RuntimeError('Verified protection artifact missing; start refused')
    expected=json.loads(manifest.read_text())
    path=project_path(ROOT,'server/mods')/expected['filename']
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']:
        raise RuntimeError('Protection artifact integrity failure; start refused')
    properties=read_properties()
    if any(properties.get(k)!=v for k,v in {'online-mode':'true','gamemode':'spectator','force-gamemode':'true'}.items()):
        raise RuntimeError('Required protection settings changed; start refused')

def read_properties():
    p=project_path(ROOT,'server/server.properties')
    return java_properties.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}

def gate(closed):
    Store.atomic(project_path(ROOT,'control/roles/maintenance.json'),json.dumps({'closed':bool(closed),'at':time.time()}).encode(),0o640)

def wait_health(timeout=240):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        container=target()
        if container.status!='running':raise RuntimeError('Minecraft exited before becoming healthy')
        try:
            report=json.loads((project_path(ROOT,'control/reports/guard-status.json')).read_text())
            from .guard_health import verified
            artifact=json.loads(project_path(ROOT,'control/runtime/guard.json').read_text())
            if verified(report,artifact) and player_count() is not None:
                return report
        except (OSError,ValueError,KeyError):pass
        time.sleep(2)
    raise RuntimeError('Minecraft health verification timed out')

def graceful_stop(container):
    container.reload()
    if container.status!='running':return
    from .job_control import may_disconnect_players
    if may_disconnect_players():
        count=player_count()
        if count is None:raise RuntimeError('player_count_unknown')
        if count:
            rcon('say [MCJ Manager] Wartung startet in 10 Sekunden. Maintenance starts in 10 seconds.')
            time.sleep(10)
    # Minecraft saves all worlds during its normal shutdown. A separate flush
    # still runs inside a server tick and can trip the watchdog on slow disks.
    # stop_container waits for shutdown and accepts only a clean exit.
    stop_container(container)

@contextmanager
def exclusive():
    if not LOCK.acquire(blocking=False):raise HTTPException(409,'maintenance_busy')
    try:yield
    finally:LOCK.release()

@app.get('/network-access')
def network_access():
    container=target()
    result=game_access.read(ROOT,container.id,datetime.fromisoformat(container.attrs['State']['StartedAt'].replace('Z','+00:00')).timestamp())
    try:
        runtime=json.loads(project_path(ROOT,'control/runtime/runtime.json').read_text())
        active=json.loads(project_path(ROOT,'control/runtime/guard.json').read_text());pending=trusted_guard(runtime['version'],runtime['loader'])
        result['update_available']=pending['sha256']!=active['sha256'] and 'mcj_network_v1' in pending.get('capabilities',[])
        result['update_guard_sha256']=pending['sha256'] if result['update_available'] else None
        result['update_basis']=hashlib.sha256(json.dumps([container.id,active['sha256'],pending['sha256']]).encode()).hexdigest()
    except (OSError,ValueError,KeyError,RuntimeError):result['update_available']=False
    return result

class NetworkAccessChange(BaseModel):
    public_game:StrictBool
    basis:str

@app.post('/network-access')
def network_access_change(data:NetworkAccessChange):
    with exclusive():
        container=target()
        if container.status!='running':raise HTTPException(409,'game_access_guard_update_required')
        try:return game_access.change(ROOT,container.id,data.public_game,data.basis,datetime.fromisoformat(container.attrs['State']['StartedAt'].replace('Z','+00:00')).timestamp())
        except ValueError as exc:raise HTTPException(409,str(exc))

def archive_backup(kind,resume=True):
    BACKUPS.mkdir(parents=True,exist_ok=True)
    storage_preflight.require(ROOT,BACKUPS,'backup')
    identifier=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+secrets.token_hex(4)
    destination=BACKUPS/(identifier+'.tar.gz')
    temporary=destination.with_suffix('.partial')
    container,running=maintenance.idle_gate(sys.modules[__name__])
    gate(True);stopped_cleanly=False
    try:
        graceful_stop(container)
        stopped_cleanly=True
        with tarfile.open(temporary,'w:gz',compresslevel=1) as tar:
            for path in sorted((project_path(ROOT,'server')).rglob('*')):
                relative=path.relative_to(project_path(ROOT,'server'))
                if path.is_symlink():raise RuntimeError('Backup refused: symbolic link in server data')
                if not path.is_dir() and not path.is_file():raise RuntimeError('Backup refused: special file in server data')
                if relative.parts[0] in {'logs','crash-reports'}:continue
                tar.add(path,arcname='server/'+relative.as_posix(),recursive=False)
            runtime=project_path(ROOT,'control/runtime/runtime.json')
            if runtime.exists():tar.add(runtime,arcname='runtime.json')
            guard=project_path(ROOT,'control/runtime/guard.json')
            if guard.exists():tar.add(guard,arcname='guard.json')
            manifest=[]
            with sqlite3.connect(project_path(ROOT,'state/manager.sqlite3')) as database:
                database.row_factory=sqlite3.Row
                for directory,enabled in [('mods',True),('mods-disabled',False)]:
                    for modfile in sorted((project_path(ROOT,'server')/directory).glob('*.jar')):
                        checksum=hashlib.sha256(modfile.read_bytes()).hexdigest()
                        row=database.execute('SELECT filename,source,origin FROM mods WHERE id=?',(checksum,)).fetchone()
                        manifest.append({'sha256':checksum,'filename':row['filename'] if row else modfile.name,
                            'enabled':enabled,'source':row['source'] if row else 'unmanaged',
                            'origin':json.loads(row['origin']) if row and row['origin'] else None})
            raw=json.dumps(manifest).encode();entry=tarfile.TarInfo('mod-manifest.json');entry.size=len(raw);entry.mode=0o600
            import io
            tar.addfile(entry,io.BytesIO(raw))
            from .maintenance import store
            pack_state={'format':1,'installations':store(sys.modules[__name__]).get('pack_installations') or {}}
            raw=json.dumps(pack_state).encode();entry=tarfile.TarInfo('pack-state.json');entry.size=len(raw);entry.mode=0o600
            tar.addfile(entry,io.BytesIO(raw))
        checksum=hashlib.sha256()
        with temporary.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):checksum.update(chunk)
        with tarfile.open(temporary,'r:gz') as tar:
            members=tar.getmembers()
            if not any(x.name=='server/server.properties' for x in members):raise RuntimeError('Backup completeness check failed')
            for member in members:
                if member.isfile():
                    stream=tar.extractfile(member)
                    while stream.read(1024*1024):pass
        os.replace(temporary,destination);os.chmod(destination,0o600)
        metadata={'id':identifier,'path':destination.name,'created':time.time(),'kind':kind,'state':'verified',
                  'sha256':checksum.hexdigest(),'size':destination.stat().st_size,'verified':time.time(),
                  'expanded_size':sum(x.size for x in members),'entry_count':len(members),
                  'restore_status':'not_tested','consistency':'clean_server_shutdown','docker_image_id':container.attrs['Image']}
        Store.atomic(BACKUPS/(identifier+'.json'),json.dumps(metadata).encode())
        try:metadata['expired_archives']=prune_backups()
        except Exception as exc:
            metadata['retention_error']=type(exc).__name__
            store(sys.modules[__name__]).event('backup','backup_retention_failed',data={'error_class':type(exc).__name__})
        return metadata
    finally:
        if temporary.exists():temporary.unlink()
        if running and resume and stopped_cleanly:
            guard_integrity();container.start();wait_health()
            gate(False)

def prune_backups():
    days=14
    database=project_path(ROOT,'state/manager.sqlite3')
    if database.exists():
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
            row=db.execute("SELECT value FROM settings WHERE name='maintenance' AND secret=0").fetchone()
            if row:days=max(1,min(90,int(json.loads(row[0])['retention_days'])))
    from .backup_inventory import prune
    from .storage_admin import backup_protection
    st=maintenance.store(sys.modules[__name__])
    with st.db() as db:
        protected=backup_protection(db,BACKUPS)
        for path in project_path(ROOT,'.rollback').glob('*/journal.json'):
            if path.is_symlink() or path.stat().st_size>65536:raise ValueError('rollback_protection_unverified')
            protected.add(json.loads(path.read_text()).get('backup_id'))
        paths={row['path'] for row in db.execute('SELECT id,path FROM backups') if row['id'] in protected}
    return prune(BACKUPS,days,protected=paths)

def checked_archive(name):
    if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gz',name):raise ValueError('Invalid archive name')
    archive=BACKUPS/name
    if archive.is_symlink() or not archive.is_file():raise ValueError('Archive unavailable')
    metadata_path=BACKUPS/(name[:-7]+'.json')
    if metadata_path.is_symlink() or metadata_path.stat().st_size>65536:raise ValueError('Archive metadata unavailable')
    metadata=json.loads(metadata_path.read_text())
    from .backup_inventory import require_available
    require_available(BACKUPS,metadata)
    checksum=hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):checksum.update(chunk)
    if not hmac.compare_digest(checksum.hexdigest(),metadata['sha256']):raise RuntimeError('Backup checksum verification failed')
    return archive,metadata,metadata_path

def trusted_guard(version,loader):
    registry=project_path(ROOT,'releases/guards/registry.json')
    if registry.is_symlink():raise RuntimeError('unsafe_guard_registry')
    entries=json.loads(registry.read_text())['artifacts']
    matches=[x for x in entries if x['minecraft']==version and x['loader']==loader]
    if len(matches)!=1:raise RuntimeError('visitor_guard_adapter_missing')
    entry=matches[0]
    for artifact in [entry,*entry.get('dependencies',[])]:
        source=project_path(ROOT,artifact['path'])
        if source.is_symlink() or not source.resolve().is_relative_to((project_path(ROOT,'releases/guards')).resolve()):raise RuntimeError('unsafe_guard_artifact')
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=artifact['sha256']:raise RuntimeError('guard_artifact_integrity_failed')
    return entry

def extract_archive(name):
    archive,metadata,metadata_path=checked_archive(name)
    storage_preflight.require(ROOT,BACKUPS,'restore_test',archive)
    scratch=project_path(ROOT,'.restore-tests')/secrets.token_hex(12)
    scratch.mkdir(parents=True,mode=0o700)
    data=scratch/'data';data.mkdir(mode=0o700)
    try:return extract_archive_data(archive,metadata,metadata_path,scratch,data)
    except BaseException:
        if scratch.resolve().parent==project_path(ROOT,'.restore-tests').resolve():shutil.rmtree(scratch)
        raise

def extract_archive_data(archive,metadata,metadata_path,scratch,data):
    total=0
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
        if len(members)>300000:raise RuntimeError('Restore entry limit exceeded')
        for member in members:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or '\\' in member.name or ':' in member.name or not (member.isdir() or member.isfile()):
                raise RuntimeError('Unsafe restore archive entry')
            if member.name not in ['runtime.json','guard.json','mod-manifest.json','pack-state.json'] and path.parts[0]!='server':raise RuntimeError('Unexpected restore archive entry')
            if member.name in ['mod-manifest.json','pack-state.json'] and member.size>8*1024*1024:raise RuntimeError('Backup management metadata limit exceeded')
            total+=member.size
        if total+20*1024**3>shutil.disk_usage(scratch).free:raise RuntimeError('Insufficient restore space with reserve')
        for member in members:
            path=PurePosixPath(member.name)
            target=(data.joinpath(*path.parts[1:]) if path.parts[0]=='server' else scratch/member.name)
            if member.isdir():target.mkdir(parents=True,exist_ok=True,mode=0o750)
            else:
                target.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
                with tar.extractfile(member) as source, target.open('xb') as destination:shutil.copyfileobj(source,destination)
                os.chmod(target,0o600)
    runtime=json.loads((scratch/'runtime.json').read_text())
    guard=json.loads((scratch/'guard.json').read_text())
    trusted=trusted_guard(runtime['version'],runtime['loader'])
    catalog=json.loads(project_path(ROOT,'releases/guards/registry.json').read_text())
    from .guard_artifacts import restore_current_guard
    guard=restore_current_guard(ROOT,data,guard,trusted,catalog.get('retained_artifacts',[]))
    Store.atomic(scratch/'guard.json',json.dumps(guard).encode(),0o640)
    properties=java_properties.loads((data/'server.properties').read_text(encoding='utf-8'))
    if any(properties.get(k)!=v for k,v in {'online-mode':'true','gamemode':'spectator','force-gamemode':'true'}.items()):
        raise RuntimeError('Restore lacks required protection settings')
    properties['rcon.password']=RCON
    Store.atomic(data/'server.properties',java_properties.dumps(properties).encode('utf-8'))
    return scratch,data,metadata,metadata_path

def isolated_restore_test(name):
    scratch,data,metadata,metadata_path=extract_archive(name)
    runtime_value=json.loads((scratch/'runtime.json').read_text())
    guard=trusted_guard(runtime_value['version'],runtime_value['loader'])
    image=metadata.get('docker_image_id') or target().attrs['Image']
    return isolated_data_test(scratch,data,runtime_value,guard,image,name,metadata,metadata_path)


def isolated_data_test(scratch,data,runtime_value,guard,image,name,metadata=None,metadata_path=None,keep_data=False):
    metadata=metadata if metadata is not None else {}
    runtime_value=dict(runtime_value)
    runtime=scratch/'runtime';roles=scratch/'roles';reports=scratch/'reports'
    for folder in [runtime,roles,reports]:folder.mkdir(mode=0o750)
    runtime_value['memory_mb']=3072
    Store.atomic(runtime/'runtime.json',json.dumps(runtime_value).encode(),0o640)
    from .isolated_runtime import start_script
    script=start_script(data,runtime_value,project_path(ROOT,'control/runtime/start.sh').read_bytes())
    Store.atomic(runtime/'start.sh',script,0o640)
    Store.atomic(runtime/'guard.sha256',(guard['sha256']+'  '+guard['filename']+'\n').encode(),0o640)
    Store.atomic(roles/'roles.json',b'{}',0o640);Store.atomic(roles/'maintenance.json',b'{"closed":true}',0o640)
    host_root=os.environ.get('HOST_PROJECT_ROOT','/volume1/docker/minecraftjava')
    def host(path):return str(Path(host_root)/path.relative_to(ROOT))
    container=None
    try:
        from .job_control import phase
        phase('test_starting')
        container=client.containers.run(image,detach=True,name='mcj_restore_test_'+secrets.token_hex(5),
            user=__import__('mcj.service_identity',fromlist=['user']).user(),entrypoint=['/bin/bash','/mcj/start.sh'],network_mode='none',
            environment={'EULA':'TRUE','UID':str(os.getuid()),'GID':str(os.getgid()),'ENABLE_RCON':'true','DEBUG':'false'},
            volumes={host(data):{'bind':'/data','mode':'rw'},host(runtime):{'bind':'/mcj','mode':'ro'},
                     host(roles):{'bind':'/mcj-control/roles','mode':'ro'},host(reports):{'bind':'/mcj-control/reports','mode':'rw'},
                     str(project_path(host_root,'secrets/rcon')):{'bind':'/run/secrets/rcon','mode':'ro'}},
            mem_limit='5g',nano_cpus=2_000_000_000,pids_limit=512,cap_drop=['ALL'],
            security_opt=['no-new-privileges:true'],labels={'mcj.purpose':'isolated-runtime-test','mcj.archive':name},
            log_config=docker.types.LogConfig(type='json-file',config={'max-size':'5m','max-file':'2'}))
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            container.reload()
            if container.status!='running':raise RuntimeError('Isolated restore server exited')
            try:
                report=json.loads((reports/'guard-status.json').read_text())
                from .guard_health import verified
                if verified(report,guard) and report['maintenance_closed']:
                    from .job_control import phase
                    phase('test_running')
                    probe=container.exec_run(['mc-monitor','status','--host','127.0.0.1','--port','25565'])
                    if probe.exit_code==0:
                        metadata.update(restore_status='isolated_server_verified',restore_tested=time.time(),restore_network='none',restore_published_ports=[])
                        if metadata_path:Store.atomic(metadata_path,json.dumps(metadata).encode())
                        return {'archive':name,'state':'isolated_server_verified','network':'none','published_ports':[],
                                'online_mode':True,'guard_version':report['guard_version'],'world_file_count':sum(1 for p in data.rglob('*') if p.is_file())}
            except (OSError,ValueError,KeyError):pass
            time.sleep(3)
        raise RuntimeError('Isolated restore health verification timed out')
    finally:
        if container:
            container.reload()
            if container.status=='running':stop_container(container)
            container.remove(v=True)
        resolved=scratch.resolve();boundary=(project_path(ROOT,'.restore-tests')).resolve()
        if not keep_data and resolved.parent==boundary:shutil.rmtree(resolved)

@app.get('/runtime-files')
def runtime_files():
    from .runtime_storage import inventory
    return {'files':inventory(ROOT,maintenance.store(sys.modules[__name__]).get('server'))}

@app.post('/runtime-files/cleanup')
def runtime_cleanup():
    from .runtime_storage import cleanup
    with exclusive():return cleanup(maintenance.store(sys.modules[__name__]),ROOT)
class RuntimeDelete(BaseModel):
    id:str=Field(pattern='^[0-9a-f]{32}$')
    confirmation:str|None=Field(default=None,max_length=64)
    actor:int
@app.post('/runtime-files/delete')
def runtime_delete(data:RuntimeDelete):
    from .runtime_storage import delete
    with exclusive():return delete(maintenance.store(sys.modules[__name__]),ROOT,data.id,data.actor,data.confirmation)

class WorldJob(BaseModel):
    operation:str=Field(pattern='^(change|delete|export)$')
    name:str=Field(pattern='^[A-Za-z0-9_-]{1,60}$')
    configuration:dict|None=None
    create:bool=False
    actor:int
    job_id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')
@app.post('/world/operation')
def world_operation(data:WorldJob):
    from . import world_operations
    from .job_control import operation
    st=maintenance.store(sys.modules[__name__])
    with exclusive(),st.change_lock(),operation(st,data.job_id):
        if data.operation=='change':
            target_path=project_path(ROOT,'server')/data.name
            if data.create and target_path.exists():raise ValueError('world_name_already_exists')
            if not data.create:world_operations.existing(sys.modules[__name__],data.name)
            return world_operations.change(sys.modules[__name__],data.configuration,data.actor)
        if data.operation=='delete':return world_operations.delete(sys.modules[__name__],data.name,data.actor)
        return world_operations.export(sys.modules[__name__],data.name,data.actor)

class DeleteBackups(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=100)
    confirmation:str|None=Field(default=None,max_length=64)
    actor:int
@app.post('/backup/delete')
def delete_backups(data:DeleteBackups):
    from . import storage_admin
    with exclusive():return storage_admin.delete(maintenance.store(sys.modules[__name__]),BACKUPS,'backup',data.ids,data.actor,confirmation=data.confirmation,rollback_root=project_path(ROOT,'.rollback'))

class RestoreTest(BaseModel):
    archive:str=Field(min_length=25,max_length=80)
    job_id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')
@app.post('/backup/test')
def restore_test(data:RestoreTest):
    from .job_control import operation
    with exclusive(),operation(maintenance.store(sys.modules[__name__]),data.job_id):return isolated_restore_test(data.archive)

class VersionOperation(BaseModel):
    plan_id:str=Field(pattern='^[0-9a-f]{32}$')
    actor:int|None=None
    job_id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')
@app.post('/version/test')
def version_test(data:VersionOperation):
    from .job_control import operation
    with exclusive(),operation(maintenance.store(sys.modules[__name__]),data.job_id):return maintenance.test_version(sys.modules[__name__],data.plan_id,data.actor)

@app.post('/version/apply')
def version_apply(data:VersionOperation):
    from .job_control import operation
    with exclusive(),operation(maintenance.store(sys.modules[__name__]),data.job_id):return maintenance.apply_change(sys.modules[__name__],'version',data.actor,identifier=data.plan_id)

class SettingsApply(BaseModel):
    configuration:dict
    based_on:str
    actor:int
    include_pending_mods:bool=False
    mod_fingerprint:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    guard_sha256:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    job_id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')
@app.post('/settings/apply')
def settings_apply(data:SettingsApply):
    from .job_control import operation
    st=maintenance.store(sys.modules[__name__])
    with exclusive(),st.change_lock(),operation(st,data.job_id):
        if data.based_on!=json.dumps(st.get('server'),sort_keys=True):raise ValueError('settings_job_stale')
        from .player_admission import opens_to_new_players,require_verified
        if opens_to_new_players(st.get('server'),data.configuration):
            # Recheck the exact active artifact when a queued job starts, not only when planned.
            require_verified(protection_readiness(operation_locked=True))
        if data.guard_sha256 is not None:
            current=st.get('server')
            if trusted_guard(current['version'],current['loader'])['sha256']!=data.guard_sha256:raise ValueError('protection_update_changed')
        if data.include_pending_mods:
            from .mods import fingerprint
            if data.mod_fingerprint!=fingerprint(st):raise ValueError('mod_plan_stale')
        return maintenance.apply_change(sys.modules[__name__],'combined' if data.include_pending_mods else 'settings',data.actor,configuration=data.configuration)

class ModApply(BaseModel):
    actor:int|None=None
    fingerprint:str=Field(pattern='^[0-9a-f]{64}$')
    selection:list[str]|None=Field(default=None,max_length=100)
    job_id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')
@app.post('/mods/apply')
def mod_apply(data:ModApply):
    from .job_control import operation
    with exclusive(),maintenance.store(sys.modules[__name__]).change_lock(),operation(maintenance.store(sys.modules[__name__]),data.job_id):
        from .mods import fingerprint
        if data.fingerprint!=fingerprint(maintenance.store(sys.modules[__name__])):raise ValueError('mod_plan_stale')
        if data.selection is not None and any(not re.fullmatch('[0-9a-f]{64}',x) for x in data.selection):raise ValueError('mod_plan_stale')
        return maintenance.apply_change(sys.modules[__name__],'mods',data.actor,selection=data.selection)

class RestoreApply(BaseModel):
    archive:str=Field(min_length=25,max_length=80)
    actor:int|None=None
    job_id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')
@app.post('/backup/restore')
def restore_apply(data:RestoreApply):
    from .job_control import operation
    with exclusive(),operation(maintenance.store(sys.modules[__name__]),data.job_id):return maintenance.apply_change(sys.modules[__name__],'restore',data.actor,archive=data.archive)

@app.get('/status')
def status():
    container=target();state=container.attrs['State'];result={
        'container_status':container.status,'started_at':state.get('StartedAt'),'restart_count':container.attrs['RestartCount'],
        'service':container.labels['com.docker.compose.service'],'project':container.labels['com.docker.compose.project'],
        'players_online':0 if container.status in ['exited','created'] else None,'tps':None,'mspt':None,'cpu_percent':None,'cpu_capacity':None,'cpu_normalized_percent':None,'memory_used':None,'memory_limit':None,
        'disk':shutil.disk_usage(ROOT)._asdict(),'backup_disk':shutil.disk_usage(BACKUPS)._asdict(),
        'maintenance_busy':LOCK.locked(),'public_game_bound':any(b.get('HostIp') not in ['127.0.0.1','::1'] for values in (container.attrs['HostConfig'].get('PortBindings') or {}).values() for b in (values or [])),
        'visitor_test':'not_verified'}
    try:
        runtime=json.loads((project_path(ROOT,'control/runtime/runtime.json')).read_text())
        result['runtime']={key:runtime.get(key) for key in ['version','java','loader','loader_version']}
    except (OSError,ValueError):result['runtime']=None
    if container.status=='running':
        stats=status_samples.collect(container)
        result.update(normalized_cpu(stats,container.attrs['HostConfig']))
        cpu=stats.get('cpu_stats',{});pre=stats.get('precpu_stats',{})
        usage=cpu.get('cpu_usage',{}).get('total_usage',0)-pre.get('cpu_usage',{}).get('total_usage',0)
        system=cpu.get('system_cpu_usage',0)-pre.get('system_cpu_usage',0)
        if pre.get('system_cpu_usage') is not None and system>0 and usage>=0:result['cpu_percent']=round(usage/system*cpu.get('online_cpus',1)*100,2)
        memory=stats.get('memory_stats',{});result['memory_used']=memory.get('usage');result['memory_limit']=memory.get('limit')
        result['players_online']=player_count()
        try:
            report=json.loads((project_path(ROOT,'control/reports/guard-status.json')).read_text())
            if time.time()-report['at']<15:result.update({k:report.get(k) for k in ['tps','mspt','guard_version','guard_protocol','maintenance_closed']})
        except (OSError,ValueError):pass
    return result

class Command(BaseModel):command:str=Field(min_length=1,max_length=2000)
@app.get('/maintenance-readiness')
def maintenance_readiness():
    return protection_readiness()

def protection_readiness(operation_locked=False):
    result={'ready':False,'public_game_bound':True,'client_permissions':'not_claimed'}
    try:
        container=target()
        result['public_game_bound']=any(x.get('HostIp') not in ['127.0.0.1','::1'] for values in (container.attrs['HostConfig'].get('PortBindings') or {}).values() for x in (values or []))
        if container.status!='running' or (LOCK.locked() and not operation_locked):return result
        runtime=json.loads((project_path(ROOT,'control/runtime/runtime.json')).read_text())
        guard=json.loads((project_path(ROOT,'control/runtime/guard.json')).read_text())
        trusted=trusted_guard(runtime['version'],runtime['loader'])
        if guard['sha256']!=trusted['sha256']:return result
        guard_integrity()
        report=json.loads((project_path(ROOT,'control/reports/guard-status.json')).read_text())
        from .guard_health import verified
        result['ready']=bool(verified(report,guard) and not report['maintenance_closed'] and player_count() is not None)
        result['guard_sha256']=guard['sha256']
        from .player_admission import guard_matches_runtime
        result['visitor_verified']=(guard_matches_runtime(runtime,trusted)
                                    and trusted.get('visitor_verified') is True
                                    and trusted.get('visitor_client_test')=='passed')
    except (OSError,ValueError,RuntimeError,KeyError):pass
    return result

@app.post('/console')
def console(data:Command):
    with exclusive():return {'output':rcon(data.command)}

class Operation(BaseModel):
    operation:str=Field(pattern='^(start|stop|restart)$')
    job_id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')
@app.post('/server')
def operation(data:Operation):
    from .job_control import operation as job_context
    with exclusive(),job_context(maintenance.store(sys.modules[__name__]),data.job_id):
        container=target()
        if data.operation=='start':
            guard_integrity();gate(True);container.start();wait_health();gate(False)
        else:
            maintenance.idle_gate(sys.modules[__name__])
            graceful_stop(container)
            if data.operation=='restart':guard_integrity();container.start();wait_health();gate(False)
        return {'ok':True,'operation':data.operation}

class Backup(BaseModel):kind:str=Field(default='manual',pattern='^[a-z_]{1,30}$')
@app.post('/backup')
def backup(data:Backup):
    with exclusive():return archive_backup(data.kind)

class StorageForecast(BaseModel):
    kind:str
    archive:str|None=None

@app.post('/storage/preflight')
def storage_forecast(data:StorageForecast):
    archive=checked_archive(data.archive)[0] if data.kind in {'restore','restore_test'} and data.archive else None
    return storage_preflight.forecast(ROOT,BACKUPS,data.kind,archive)

@app.get('/properties')
def properties():
    from .server_settings import SECRET_KEYS
    return {k:v for k,v in read_properties().items() if k not in SECRET_KEYS}

from . import game_rules

def active_rule_context():
    container=target()
    if container.status!='running':raise ValueError('game_rules_server_offline')
    runtime=json.loads(project_path(ROOT,'control/runtime/runtime.json').read_text())
    return runtime['version'],read_properties().get('level-name','world'),container.id

@app.get('/game-rules')
def read_game_rules():
    with exclusive():return game_rules.read(rcon,*active_rule_context())

@app.post('/game-rules')
def save_game_rule(data:game_rules.Change):
    with exclusive():return game_rules.apply(rcon,data,*active_rule_context())

@app.get('/worlds')
def world_inventory():
    from .worlds import inventory
    return {'worlds':inventory(project_path(ROOT,'server'))}

@app.get('/players')
def players():
    from .player_presence import query,reconcile
    container=target()
    try:report=json.loads((project_path(ROOT,'control/reports/players.json')).read_text())
    except (OSError,ValueError):report={'players':[]}
    online,reason,attempts=query(rcon) if container.status=='running' else ([],None,0)
    report=reconcile(report,online)
    report.update(presence_error_class=reason,presence_attempts=attempts)
    try:grants=json.loads((project_path(ROOT,'control/roles/roles.json')).read_text())
    except (OSError,ValueError):grants={}
    for player in report['players']:
        grant=grants.get(player['uuid'],{})
        player.update(role=grant.get('role','visitor'),banned=bool(grant.get('banned',False)),
            ban_reason=grant.get('reason',''),op=bool(grant.get('op',False)),whitelisted=bool(grant.get('whitelisted',False)))
    return report

class PlayerJournal(BaseModel):cursor:dict=Field(default_factory=dict)
@app.post('/player-events')
def player_events(data:PlayerJournal):
    from .player_events import read_batch
    return read_batch(project_path(ROOT,'control/reports/player-events.jsonl'),data.cursor)

class PlayerAction(BaseModel):
    uuid:str=Field(min_length=36,max_length=36)
    action:str=Field(pattern='^(role|kick|ban|unban|whitelist|op)$')
    role:str=Field(default='visitor',pattern='^(visitor|player|moderator|administrator)$')
    enabled:bool=False
    reason:str=Field(default='',max_length=150)

def role_permissions_supported():
    try:
        guard=json.loads(project_path(ROOT,'control/runtime/guard.json').read_text())
        if 'mcj_roles_v1' not in guard.get('capabilities',[]):return False
        guard_integrity()
        return True
    except (OSError,ValueError,RuntimeError):return False

@app.get('/role-permissions')
def read_role_permissions():
    try:value=role_permissions.read(ROOT)
    except ValueError:value={'format':1,'roles':role_permissions.defaults(),'configured':False,'error':'invalid_role_permissions'}
    return {**value,'supported':role_permissions_supported(),'abilities':list(role_permissions.ABILITIES)}

class RolePermissions(BaseModel):roles:dict

@app.post('/role-permissions')
def save_role_permissions(data:RolePermissions):
    with exclusive():
        if not role_permissions_supported():raise ValueError('permission_adapter_not_available')
        return {**role_permissions.write(ROOT,data.roles),'supported':True,'restart_required':False}

@app.post('/player')
def player_action(data:PlayerAction):
    if str(uuid.UUID(data.uuid))!=data.uuid:raise ValueError('Canonical Minecraft UUID required')
    if any(x in data.reason for x in ['\r','\n','\x00']):raise ValueError('Invalid moderation reason')
    if data.action in ['ban','unban'] and not data.reason.strip():raise ValueError('Moderation reason required')
    with exclusive():
        known=players().get('players',[])
        matches=[p for p in known if p['uuid']==data.uuid]
        if len(matches)!=1:raise ValueError('Player UUID not observed by this server')
        player=matches[0];name=player['name']
        if not re.fullmatch('[A-Za-z0-9_]{1,16}',name):raise ValueError('Invalid recorded Minecraft name')
        if data.action=='kick':
            if not player.get('online_since'):raise ValueError('Player is offline')
            return {'output':rcon('kick '+name+' '+(data.reason or 'Administration')),'uuid':data.uuid}
        grants_path=project_path(ROOT,'control/roles/roles.json')
        if grants_path.is_symlink():raise ValueError('Unsafe role configuration link')
        grants=json.loads(grants_path.read_text())
        grant=grants.get(data.uuid,{'role':'visitor','op':False,'banned':False})
        if data.action=='role':
            grant['role']=data.role
            if data.role!='administrator':grant['op']=False
        elif data.action=='ban':grant.update(banned=True,reason=data.reason)
        elif data.action=='unban':grant.update(banned=False,reason='')
        elif data.action=='op':
            if data.enabled and grant['role']!='administrator':raise ValueError('Minecraft OP requires Minecraft administrator role')
            grant['op']=data.enabled
        elif data.action=='whitelist':
            path=project_path(ROOT,'server/whitelist.json')
            if path.is_symlink():raise ValueError('Unsafe whitelist link')
            values=json.loads(path.read_text()) if path.exists() else []
            values=[p for p in values if p['uuid']!=data.uuid]
            if data.enabled:values.append({'uuid':data.uuid,'name':name})
            Store.atomic(path,json.dumps(values).encode(),0o600)
            if target().status=='running':rcon('whitelist reload')
            grant['whitelisted']=data.enabled
        grants[data.uuid]=grant
        Store.atomic(grants_path,json.dumps(grants).encode(),0o640)
        if data.action=='ban' and player.get('online_since'):
            try:rcon('kick '+name+' '+(data.reason or 'Gesperrt / Banned'))
            except Exception:pass
        return {'state':'recorded','uuid':data.uuid,'name':name,'grant':grant,'enforcement':'server_guard'}

@app.exception_handler(Exception)
async def error(request,exc):
    from starlette.responses import JSONResponse
    # Structured error classes; no trace, Docker response or environment is exposed.
    safe=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__
    safe=safe.replace(TOKEN,'[REDACTED]').replace(RCON,'[REDACTED]')
    return JSONResponse({'detail':'controller_operation_failed','reason':safe[:250]},status_code=503)

@app.get('/client-pack/snapshot')
def client_pack_snapshot():
    st=maintenance.store(sys.modules[__name__])
    with exclusive(),st.change_lock():return client_packs.snapshot(ROOT,st)

@app.post('/client-pack/delete')
def client_pack_delete(data:DeleteBackups):
    # The process which reads the server fingerprint also owns the mutation lock.
    # A manager-held lock around a controller RPC would block that RPC itself.
    st=maintenance.store(sys.modules[__name__])
    with exclusive():return client_packs.delete_old(ROOT,st,data.ids,data.actor,confirmation=data.confirmation)

class ClientSide(BaseModel):
    sha256:str=Field(pattern='^[0-9a-f]{64}$')
    side:Literal['auto','required','optional','unsupported']
    basis:str=Field(pattern='^[0-9a-f]{64}$')
    actor:int=Field(ge=1)

@app.post('/client-pack/side')
def client_pack_side(data:ClientSide):
    st=maintenance.store(sys.modules[__name__])
    with exclusive():return client_packs.set_side(ROOT,st,data.sha256,data.side,data.basis,data.actor)

class ClientPatch(BaseModel):
    sha256:str=Field(pattern='^[0-9a-f]{64}$')

@app.post('/client-pack/patched-file')
def client_patch_file(data:ClientPatch):
    with exclusive():return client_packs.patched_bytes(ROOT,data.sha256)

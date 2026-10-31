"""One-shot UGOS app update. No listener and no UGOS bind to application data.

Only the two existing app services may be recreated. Compose input is frozen in a
private helper and must match the hashes on the currently deployed containers.
"""
import copy,hashlib,json,os,re,secrets,shutil,sqlite3,stat,subprocess,sys,tempfile,threading,time
from contextlib import closing
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from mcj import __version__

SERVICES=('manager','controller','minecraft')
SOURCE='https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager'
IMAGE=re.compile(r'sha256:[0-9a-f]{64}')

def docker(*args,timeout=150,check=True,**kwargs):
    return subprocess.run(['docker',*args],check=check,capture_output=True,text=True,timeout=timeout,**kwargs)

def inspect(name):return json.loads(docker('inspect',name).stdout)[0]

def discover(items):
    if len(items)!=3:raise ValueError('update_service_scope_invalid')
    rows={x['Config']['Labels'].get('com.docker.compose.service'):x for x in items}
    if set(rows)!=set(SERVICES):raise ValueError('update_service_scope_invalid')
    lab=rows['manager']['Config']['Labels'];project=lab.get('com.docker.compose.project','');compose=lab.get('com.docker.compose.project.config_files','')
    root=str(PurePosixPath(compose).parent)
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{1,63}',project) or not re.fullmatch(r'/volume[1-9][0-9]*/[A-Za-z0-9_/-]+/docker-compose.yaml',compose) or '..' in PurePosixPath(compose).parts:raise ValueError('update_project_identity_invalid')
    for service,obj in rows.items():
        labels=obj['Config']['Labels']
        if (obj['Name']!='/mcj_'+service or labels.get('com.docker.compose.project')!=project or labels.get('com.docker.compose.project.config_files')!=compose or labels.get('com.docker.compose.project.working_dir')!=root):raise ValueError('update_project_identity_invalid')
        if not obj['State'].get('Running') or obj['State'].get('Health',{}).get('Status')!='healthy':raise ValueError('update_services_not_healthy')
        if not re.fullmatch('[0-9a-f]{64}',labels.get('com.docker.compose.config-hash','')):raise ValueError('update_compose_identity_missing')
    for service in ('manager','controller'):
        labels=rows[service]['Config']['Labels'];version=labels.get('org.opencontainers.image.version','')
        if labels.get('org.opencontainers.image.source')!=SOURCE or not re.fullmatch(r'1\.\d+\.\d+',version):raise ValueError('update_source_unverified')
        if tuple(map(int,version.split('.')))>tuple(map(int,__version__.split('.'))):raise ValueError('update_downgrade_refused')
    if rows['manager']['Image']!=rows['controller']['Image']:raise ValueError('update_app_images_differ')
    mounted=[m for m in rows['manager']['Mounts'] if m['Destination']=='/project/manager/state']
    if len(mounted)!=1 or mounted[0]['Type']!='bind' or mounted[0]['Source']!=root+'/manager/state':raise ValueError('update_state_mount_invalid')
    return {'project':project,'root':root,'compose':compose,'ids':{s:rows[s]['Id'] for s in SERVICES},'images':{s:rows[s]['Image'] for s in SERVICES}}

def read_file(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:raise ValueError('update_file_invalid')
        raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('update_file_limit')
    return raw,info

def key_facts(root,owner=(1009,10)):
    result={}
    for name in ('encryption','rpc','rcon'):
        raw,info=read_file(root/'manager/secrets'/name,256)
        if not raw or (info.st_uid,info.st_gid)!=tuple(owner) or stat.S_IMODE(info.st_mode)&0o137:raise ValueError('update_secret_permissions_invalid')
        result[name]=(hashlib.sha256(raw).hexdigest(),info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
    return result

def validate_definition(value):
    if not isinstance(value,dict) or set(value)-{'name','services','networks'} or set(value.get('services',{}))!=set(SERVICES):raise ValueError('update_definition_invalid')
    for service,row in value['services'].items():
        if row.get('container_name')!='mcj_'+service or row.get('profiles') or row.get('extends') or row.get('scale',1)!=1 or row.get('deploy',{}).get('replicas',1)!=1:raise ValueError('update_definition_invalid')
        if row.get('env_file') or row.get('label_file'):raise ValueError('update_external_file_refused')
    return value

def validate_environment(raw):
    value=raw.decode('utf-8')
    for line in value.splitlines():
        if not line.strip() or line.startswith('#'):continue
        if re.fullmatch(r'MCJ_GAME_MEMORY_MB=[0-9]{4,5}',line):continue
        if re.fullmatch(r'MCJ_MANAGER_IMAGE=(?:mcj-manager:(?:0\.1|1\.[0-9]+\.[0-9]+)|railsimulatornet/ugreen-nas-minecraft-java-manager:(?:1\.[0-9]+\.[0-9]+|sha-[0-9a-f]{40}))',line):continue
        if re.fullmatch(r'MCJ_GAME_IMAGE=itzg/minecraft-server:java(?:17|21|25)(?:@sha256:[0-9a-f]{64}|-mcj-[0-9a-f]{12})',line):continue
        raise ValueError('update_environment_invalid')
    return value

def freeze_networks(value,items):
    result=copy.deepcopy(value)
    names=set()
    for key,cfg in value.get('networks',{}).items():
        name=cfg.get('name')
        if not name or not re.fullmatch('[a-zA-Z0-9_.-]{1,128}',name):raise ValueError('update_network_invalid')
        network=json.loads(docker('network','inspect',name).stdout)[0]
        attached=[obj for obj in items if key in value['services'][obj['Config']['Labels']['com.docker.compose.service']].get('networks',{})]
        if not attached or any(obj['NetworkSettings']['Networks'].get(name,{}).get('NetworkID')!=network['Id'] for obj in attached):raise ValueError('update_network_identity_changed')
        result['networks'][key]={'name':name,'external':True};names.add(name)
    if set().union(*(set(x['NetworkSettings']['Networks']) for x in items))!=names:raise ValueError('update_network_scope_invalid')
    return result

def invoke(image,scope,definition,environment,action):
    # The path matches the real labels, but is a private tmpfs in this helper.
    payload=dict(scope,definition=definition,environment=environment,action=action)
    return docker('run','--rm','-i','--network','none','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--memory','256m','--pids-limit','64','--tmpfs','/tmp:rw,nosuid,noexec,size=64m','--tmpfs',scope['root']+':rw,nosuid,noexec,size=4m,mode=0700',
        '-v','/var/run/docker.sock:/var/run/docker.sock','--entrypoint','python',image,'/opt/mcj/tools/app_update_compose.py',input=json.dumps(payload)).stdout

def atomic(path,raw,mode=0o640,owner=(0,10)):
    if path.is_symlink():raise ValueError('update_symlink_refused')
    temporary=path.with_name('.'+path.name+'.'+secrets.token_hex(12))
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchown(stream.fileno(),*owner);os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()

def rollback_parent(root,owner):
    # This parent is shared with later non-root world/mod promotions. Individual
    # app-update snapshots remain root-only; never recursively change ownership.
    control_fd=os.open(root/'mcj_controller',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        created=False
        try:os.mkdir('.rollback',mode=0o700,dir_fd=control_fd);created=True
        except FileExistsError:pass
        fd=os.open('.rollback',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=control_fd)
        try:
            info=os.fstat(fd)
            if (info.st_uid,info.st_gid) not in (tuple(owner),(0,0)) and not (created and info.st_uid==os.geteuid()):raise ValueError('update_rollback_owner_invalid')
            os.fchown(fd,*owner);os.fchmod(fd,0o700)
        finally:os.close(fd)
    finally:os.close(control_fd)
    return root/'mcj_controller/.rollback'

class Lease:
    def __init__(self,state,gid=10):self.path=state/'.deployment-hold.json';self.identifier=secrets.token_hex(16);self.done=threading.Event();self.failed=False;self.owner=(0,gid)
    def value(self):return json.dumps({'purpose':'app-deployment','lease_id':self.identifier,'until':time.time()+180}).encode()
    def __enter__(self):
        if self.path.exists():
            raw,info=read_file(self.path,1024);old=json.loads(raw)
            if info.st_uid!=0 or old.get('purpose')!='app-deployment' or time.time()-info.st_mtime<300 or type(old.get('until')) not in (int,float) or old['until']>=time.time():raise ValueError('update_already_running')
            self.path.unlink()
        fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
        with os.fdopen(fd,'wb') as stream:os.fchown(stream.fileno(),*self.owner);stream.write(self.value())
        self.thread=threading.Thread(target=self.renew,daemon=True);self.thread.start();return self
    def renew(self):
        while not self.done.wait(30):
            try:self.check();atomic(self.path,self.value(),owner=self.owner)
            except Exception:self.failed=True;return
    def check(self):
        value=json.loads(read_file(self.path,1024)[0])
        if self.failed or value.get('lease_id')!=self.identifier or value.get('until',0)<=time.time():raise ValueError('update_lease_lost')
    def __exit__(self,*args):
        self.done.set();self.thread.join()
        if self.path.exists() and json.loads(read_file(self.path,1024)[0]).get('lease_id')==self.identifier:self.path.unlink()

def principals(db):
    return (db.execute('SELECT id,username,email,password,admin,force_password,factor,totp,enabled,generation FROM users ORDER BY id').fetchall(),
            db.execute('SELECT name,value,secret FROM settings WHERE secret=1 ORDER BY name').fetchall())

def healthy(image,check=lambda:None):
    end=time.monotonic()+90
    while time.monotonic()<end:
        check()
        items=[inspect('mcj_'+s) for s in ('manager','controller')]
        if all(x['Image']==image and x['State'].get('Health',{}).get('Status')=='healthy' and x['State'].get('Running') for x in items):return
        if any(x['State']['Status'] in ('dead','exited') for x in items):break
        time.sleep(2)
    raise ValueError('update_health_failed')

def work(scope,image):
    items=[inspect('mcj_'+s) for s in SERVICES]
    if discover(items)!=scope:raise ValueError('update_project_identity_changed')
    root=Path(scope['root']);state=root/'manager/state';compose=Path(scope['compose'])
    if any(p.is_symlink() for p in [root,*root.parents,state,root/'manager',root/'manager/secrets']):raise ValueError('update_symlink_refused')
    original,info=read_file(compose,262144);definition=validate_definition(json.loads(original))
    if definition.get('name',scope['project'])!=scope['project']:raise ValueError('update_project_identity_invalid')
    env_raw,_=read_file(root/'.env',8192) if (root/'.env').exists() else (b'',None)
    environment=validate_environment(env_raw)
    selected_user=definition['services']['manager'].get('user','1009:10')
    if not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*',selected_user):raise ValueError('update_service_identity_invalid')
    owner=tuple(map(int,selected_user.split(':')))
    keys=key_facts(root,owner)
    database=state/'manager.sqlite3';database_size=database.stat().st_size
    if database_size>128*1024**2 or shutil.disk_usage(root).free<max(32*1024**2,database_size*3):raise ValueError('update_backup_space_insufficient')
    hashes=dict(line.split() for line in invoke(image,scope,definition,environment,'hash').splitlines())
    if hashes!={x['Config']['Labels']['com.docker.compose.service']:x['Config']['Labels']['com.docker.compose.config-hash'] for x in items}:raise ValueError('update_compose_changed_since_deployment')
    frozen=freeze_networks(definition,items)
    if all(scope['images'][s]==image for s in ('manager','controller')):
        print('Bereits aktuell / Already up to date',flush=True);return {'phase':'complete','noop':True}
    wanted=copy.deepcopy(frozen);persisted=copy.deepcopy(frozen);rollback=copy.deepcopy(frozen)
    for service in ('manager','controller'):
        for cfg in (wanted,persisted):cfg['services'][service].update(image=image,pull_policy='never');cfg['services'][service].pop('build',None)
        rollback['services'][service].update(image=scope['images'][service],pull_policy='never');rollback['services'][service].pop('build',None)
    database=state/'manager.sqlite3';saved_mode=database.stat();touched=False;stop_attempted=False
    report={'phase':'checking','progress':10,'target_version':__version__,'source':'ugos','updated':time.time()}
    def status(phase,progress,**extra):
        report.update(phase=phase,progress=progress,updated=time.time(),**extra);atomic(state/'application-update.json',json.dumps(report).encode(),owner=(0,owner[1]))
        print(str(progress)+'% '+phase,flush=True)
    with Lease(state,owner[1]) as lease:
        status('checking',10)
        scratch=Path(tempfile.mkdtemp(prefix='mcj-update-'))
        snapshot=scratch/'manager.sqlite3'
        try:
            lease.check()
            rollback_base=rollback_parent(root,owner)
            with closing(sqlite3.connect(database,timeout=10)) as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT 1 FROM jobs WHERE state='running'").fetchone() or db.execute("SELECT 1 FROM backups WHERE state='running'").fetchone():raise ValueError('update_maintenance_busy')
                # Stop the old worker while its atomic job-claim lock is held.
                lease.check();stop_attempted=True;docker('stop','--time','30',scope['ids']['manager'],timeout=45)
            docker('stop','--time','30',scope['ids']['controller'],timeout=45)
            status('backup',30)
            with closing(sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True)) as db,closing(sqlite3.connect(snapshot)) as target:
                before=principals(db);db.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('update_backup_invalid')
            folder=rollback_base/('ugos-app-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+secrets.token_hex(4))
            folder.mkdir(mode=0o700)
            atomic(folder/'manager.sqlite3',snapshot.read_bytes(),0o600,(0,0));atomic(folder/'docker-compose.yaml',original,0o600,(0,0))
            atomic(folder/'environment',env_raw,0o600,(0,0));backup_hash=hashlib.sha256(snapshot.read_bytes()).hexdigest()
            if hashlib.sha256(read_file(folder/'manager.sqlite3',256*1024**2)[0]).hexdigest()!=backup_hash:raise ValueError('update_backup_invalid')
            status('updating',55,rollback_folder=str(folder))
            if read_file(compose,262144)[0]!=original or ((root/'.env').exists() and read_file(root/'.env',8192)[0]!=env_raw) or key_facts(root,owner)!=keys:raise ValueError('update_source_changed')
            touched=True;atomic(compose,json.dumps(persisted,indent=2).encode(),stat.S_IMODE(info.st_mode),(info.st_uid,info.st_gid))
            lease.check();invoke(image,scope,wanted,environment,'up');status('health',80);healthy(image,lease.check)
            with closing(sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True)) as db:
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok' or principals(db)!=before:raise ValueError('update_data_verification_failed')
            game=inspect('mcj_minecraft');prior=next(x for x in items if x['Name']=='/mcj_minecraft')
            if any(game[k]!=prior[k] for k in ('Id','Image')) or game['State']['StartedAt']!=prior['State']['StartedAt'] or key_facts(root,owner)!=keys:raise ValueError('update_runtime_identity_changed')
            status('complete',100,services_healthy=True,credentials_preserved=True,game_unchanged=True)
        except Exception:
            if touched:
                invoke(image,scope,wanted,environment,'stop')
                failed=folder/'failed-manager.sqlite3'
                if database.exists():
                    try:shutil.copyfile(database,failed);failed.chmod(0o600)
                    except OSError:pass  # Diagnostic copy must not prevent recovery.
                for suffix in ('-wal','-shm'):
                    path=Path(str(database)+suffix)
                    if path.is_symlink():raise ValueError('update_symlink_refused')
                    if path.exists():path.unlink()
                atomic(database,snapshot.read_bytes(),stat.S_IMODE(saved_mode.st_mode),(saved_mode.st_uid,saved_mode.st_gid))
                restored=copy.deepcopy(frozen)
                for service in ('manager','controller'):
                    restored['services'][service].update(image=scope['images'][service],pull_policy='never');restored['services'][service].pop('build',None)
                atomic(compose,json.dumps(restored,indent=2).encode(),stat.S_IMODE(info.st_mode),(info.st_uid,info.st_gid))
                invoke(image,scope,rollback,environment,'up');healthy(scope['images']['manager']);status('rolled_back',0,rolled_back=True)
            elif stop_attempted:
                docker('start',scope['ids']['controller']);docker('start',scope['ids']['manager']);healthy(scope['images']['manager']);status('failed',0)
            else:status('failed',0)
            raise
        finally:shutil.rmtree(scratch)
    return report

def launcher():
    own=inspect(os.environ['HOSTNAME']);labels=own['Config'].get('Labels') or {};image=own['Image']
    if labels.get('mcj.purpose')!='application-update' or own['HostConfig'].get('NetworkMode')!='none' or own['HostConfig'].get('Privileged'):raise ValueError('update_launcher_invalid')
    if len(own['Mounts'])!=1 or own['Mounts'][0]['Source']!='/var/run/docker.sock':raise ValueError('update_launcher_mounts_invalid')
    meta=json.loads(docker('image','inspect',image).stdout)[0]['Config']['Labels']
    if meta.get('org.opencontainers.image.version')!=__version__ or meta.get('org.opencontainers.image.source')!=SOURCE or not re.fullmatch('[0-9a-f]{40}',meta.get('org.opencontainers.image.revision','')):raise ValueError('update_image_unverified')
    scope=discover([inspect('mcj_'+s) for s in SERVICES])
    command=['run','--rm','-i','--name','mcj_app_update_'+own['Id'][:12],'--label','mcj.purpose=application-update-worker','--label','mcj.update.launcher='+own['Id'],
        '--network','none','--user','0:0','--read-only','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','FOWNER','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges:true',
        '--memory','512m','--pids-limit','64','--tmpfs','/tmp:rw,nosuid,noexec,size=256m','-v','/var/run/docker.sock:/var/run/docker.sock','-v',scope['root']+':'+scope['root'],
        '--entrypoint','python',image,'/opt/mcj/tools/app_update.py','--worker']
    result=docker(*command,input=json.dumps({'scope':scope,'launcher':own['Id']}),timeout=420,check=False)
    print(result.stdout,flush=True)
    if result.returncode:
        match=re.search(r'MCJ_UPDATE_ERROR=([a-z_]{3,80})',result.stderr)
        raise ValueError(match[1] if match else 'update_failed')

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        raw=sys.stdin.buffer.read(16385)
        if len(raw)>16384:raise ValueError('update_scope_invalid')
        context=json.loads(raw);own=inspect(os.environ['HOSTNAME']);parent=inspect(context['launcher']);labels=own['Config'].get('Labels') or {}
        if labels.get('mcj.purpose')!='application-update-worker' or labels.get('mcj.update.launcher')!=parent['Id'] or own['Image']!=parent['Image'] or parent['Config']['Labels'].get('mcj.purpose')!='application-update':raise ValueError('update_worker_invalid')
        work(context['scope'],own['Image'])
    else:launcher()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[a-z_]{3,80}',str(exc)) else 'update_failed'
        messages={
            'update_maintenance_busy':'Wartung läuft. Warte auf ihren Abschluss und starte die Aktualisierung erneut. / Maintenance is running. Wait for completion, then retry.',
            'update_services_not_healthy':'Die bestehende Installation ist nicht vollständig bereit. Prüfe die Container in UGOS. / The existing installation is not fully healthy. Check its containers in UGOS.',
            'update_compose_changed_since_deployment':'Die Compose-Datei stimmt nicht mit den laufenden Containern überein. Die Übernahme wurde abgebrochen. / The Compose file differs from the running containers. No update was applied.',
            'update_secret_permissions_invalid':'Ein Schlüssel hat unerwartete Dateirechte. Die Aktualisierung verändert diese Rechte nicht und wurde angehalten. / A key has unexpected file permissions. The update leaves those permissions unchanged and has stopped.',
            'update_backup_space_insufficient':'Für die geprüfte Sicherung fehlt Speicherplatz. / Insufficient space for a verified backup.',
            'update_rollback_owner_invalid':'Der Rückfallordner gehört nicht zu diesem Dienst. Die Aktualisierung wurde vor dem Dienststopp angehalten. / The rollback folder has an unexpected owner. The update stopped before stopping services.',
            'update_health_failed':'Die neue Version ist nicht gesund gestartet. Prüfe den Rückfallstatus im Manager. / The new version did not start successfully. Check rollback status in the manager.',
            'update_already_running':'Eine andere Aktualisierung läuft noch. / Another update is still running.'}
        print('MCJ_UPDATE_ERROR='+code,file=sys.stderr)
        print(messages.get(code,'Aktualisierung angehalten. Bestehende Daten bleiben erhalten. / Update stopped. Existing data is retained.'),file=sys.stderr);raise SystemExit(1)

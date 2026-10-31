import copy,hashlib,json,os,sqlite3,stat,sys,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from contextlib import closing
from mcj import application_update as public
from test_security import environment,enroll,post
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import app_update as update

OLD='sha256:'+'a'*64;NEW='sha256:'+'d'*64

def containers(root='/volume1/docker/minecraftjava'):
    items=[]
    for n,service in enumerate(update.SERVICES):
        items.append({'Id':str(n)*64,'Name':'/mcj_'+service,'Image':OLD,'Config':{'Labels':{
            'com.docker.compose.service':service,'com.docker.compose.project':'actual_label_project',
            'com.docker.compose.project.config_files':root+'/docker-compose.yaml','com.docker.compose.project.working_dir':root,
            'com.docker.compose.config-hash':str(n+1)*64,'org.opencontainers.image.source':update.SOURCE,'org.opencontainers.image.version':'1.0.0'}},
            'State':{'Running':True,'Health':{'Status':'healthy'},'StartedAt':'unchanged-'+service},
            'Mounts':[{'Type':'bind','Source':root+'/manager/state','Destination':'/project/manager/state'}],
            'NetworkSettings':{'Networks':{'actual_control':{'NetworkID':'network-id'}}}})
    return items

def definition():
    return {'name':'actual_label_project','services':{s:{'container_name':'mcj_'+s,'image':OLD,'networks':{'control':None}} for s in update.SERVICES},'networks':{'control':{'name':'actual_control'}}}

def test_identity_comes_from_all_real_labels_not_directory_name():
    items=containers();scope=update.discover(items)
    assert scope['project']=='actual_label_project' and scope['root'].endswith('/minecraftjava')
    for field,value in [('com.docker.compose.project','foreign'),('com.docker.compose.project.config_files','/volume2/other/docker-compose.yaml'),('com.docker.compose.project.working_dir','/volume2/other')]:
        wrong=copy.deepcopy(items);wrong[1]['Config']['Labels'][field]=value
        with pytest.raises(ValueError,match='identity'):update.discover(wrong)
    wrong=copy.deepcopy(items);wrong[0]['Mounts'][0]['Source']='/volume1/foreign/state'
    with pytest.raises(ValueError,match='mount'):update.discover(wrong)
    wrong=copy.deepcopy(items);wrong[1]['Config']['Labels']['org.opencontainers.image.source']='https://untrusted.invalid'
    with pytest.raises(ValueError,match='source_unverified'):update.discover(wrong)
    wrong=copy.deepcopy(items);wrong[0]['Config']['Labels']['org.opencontainers.image.version']='1.1.0'
    with pytest.raises(ValueError,match='downgrade'):update.discover(wrong)

@pytest.mark.parametrize('change',[{'include':'https://untrusted.invalid/compose.yaml'},{'configs':{'x':{'file':'/etc/shadow'}}},{'volumes':{'x':{}}}])
def test_external_compose_input_is_refused_before_execution(change):
    with pytest.raises(ValueError,match='definition_invalid'):update.validate_definition(definition()|change)

@pytest.mark.parametrize('change',[{'profiles':['anything']},{'scale':2},{'deploy':{'replicas':2}},{'env_file':['/etc/passwd']},{'extends':{'file':'/etc/compose'}}])
def test_hidden_or_scaled_services_are_refused(change):
    cfg=definition();cfg['services']['manager'].update(change)
    with pytest.raises(ValueError):update.validate_definition(cfg)

def test_environment_cannot_control_compose_or_execute_external_commands():
    assert update.validate_environment(b'MCJ_GAME_IMAGE=itzg/minecraft-server:java25-mcj-abcdef123456\nMCJ_GAME_MEMORY_MB=8192\n')
    assert update.validate_environment(b'MCJ_MANAGER_IMAGE=mcj-manager:1.0.0\nMCJ_GAME_MEMORY_MB=8192\n')
    assert update.validate_environment(b'MCJ_MANAGER_IMAGE=mcj-manager:0.1\nMCJ_GAME_MEMORY_MB=16384\nMCJ_GAME_IMAGE=itzg/minecraft-server:java25-mcj-9c649589ff32\n')
    with pytest.raises(ValueError,match='environment_invalid'):update.validate_environment(b'MCJ_MANAGER_IMAGE=untrusted.example/image:latest\n')
    for raw in [b'COMPOSE_FILE=/other.yml',b'MCJ_GAME_IMAGE=$(touch /tmp/escape)',b'MCJ_GAME_MEMORY_MB=8192\nCOMPOSE_PROFILES=malicious']:
        with pytest.raises(ValueError,match='environment_invalid'):update.validate_environment(raw)

def test_networks_are_pinned_to_existing_attachments_and_cannot_be_created(monkeypatch):
    monkeypatch.setattr(update,'docker',lambda *a,**k:SimpleNamespace(stdout=json.dumps([{'Id':'network-id'}])))
    result=update.freeze_networks(definition(),containers())
    assert result['networks']=={'control':{'name':'actual_control','external':True}}
    wrong=containers();wrong[0]['NetworkSettings']['Networks']['actual_control']['NetworkID']='foreign'
    with pytest.raises(ValueError,match='identity_changed'):update.freeze_networks(definition(),wrong)

def test_update_template_has_no_application_data_binds_ports_or_listener():
    import yaml
    cfg=yaml.safe_load(public.template());service=cfg['services']['einrichtung']
    assert cfg['name']=='mcj_einrichtung' and service['container_name']=='mcj_einrichtung'
    assert service['volumes']==['/var/run/docker.sock:/var/run/docker.sock']
    assert service['network_mode']=='none' and not service.get('ports') and not service.get('cap_add')
    assert service['read_only'] and service['restart']=='no' and service['pull_policy']=='never'

def test_key_permissions_are_checked_without_rewriting_or_weakening_them(monkeypatch):
    facts=SimpleNamespace(st_uid=1009,st_gid=10,st_mode=0o100400)
    monkeypatch.setattr(update,'read_file',lambda *args:(b'disposable-key',facts))
    assert len(update.key_facts(Path('fixture')))==3
    for mode in [0o770,0o644,0o660,0o640]:
        facts.st_mode=0o100000|mode
        if mode==0o640:assert update.key_facts(Path('fixture'))
        else:
            with pytest.raises(ValueError,match='secret_permissions'):update.key_facts(Path('fixture'))
    facts.st_mode=0o100400;facts.st_uid=1003
    with pytest.raises(ValueError,match='secret_permissions'):update.key_facts(Path('fixture'))

def test_live_status_filters_all_private_data(tmp_path):
    store=SimpleNamespace(state=tmp_path)
    (tmp_path/'application-update.json').write_text(json.dumps({'phase':'complete','progress':100,'rollback_folder':'private-path','token':'NEVER-RETURN','credentials_preserved':True}))
    result=public.status(store)
    assert result['phase']=='complete' and result['credentials_preserved']
    assert 'private' not in json.dumps(result) and 'NEVER' not in json.dumps(result)
    (tmp_path/'application-update.json').write_text('{broken')
    assert public.status(store)['phase']=='unavailable'

def test_unreadable_update_status_is_not_reported_as_no_update(tmp_path,monkeypatch):
    store=SimpleNamespace(state=tmp_path)
    assert public.status(store)['phase']=='ready'
    monkeypatch.setattr(public.os,'open',lambda *args,**kwargs:(_ for _ in ()).throw(PermissionError()))
    assert public.status(store)['phase']=='unavailable'

def test_template_is_admin_only_and_update_lease_blocks_mutations_without_new_mfa(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    response=client.get('/api/application-update/template')
    assert response.status_code==200 and 'application-update' in response.text
    lease=st.state/'.deployment-hold.json';lease.write_text(json.dumps({'until':time.time()+90}))
    before=st.get('maintenance')
    response=post(client,'/api/settings',{'section':'maintenance','value':before},csrf)
    assert response.status_code==503 and response.json()['detail']=='application_update_running'
    assert client.get('/api/auth/me').json()['mfa_verified']
    assert client.get('/api/settings').status_code==200
    lease.unlink()
    assert post(client,'/api/settings',{'section':'maintenance','value':before},csrf).status_code==200
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/application-update/template').status_code==403

@pytest.fixture
def lifecycle(tmp_path,monkeypatch):
    root=tmp_path/'installation';state=root/'manager/state';state.mkdir(parents=True)
    (root/'mcj_controller').mkdir();dbpath=state/'manager.sqlite3'
    with closing(sqlite3.connect(dbpath)) as db:
        db.executescript('CREATE TABLE users(id,username,email,password,admin,force_password,factor,totp,enabled,generation); CREATE TABLE settings(name,value,secret); CREATE TABLE jobs(state); CREATE TABLE backups(state);')
        db.execute('INSERT INTO users VALUES(1,?,?,?,?,?,?,?,?,?)',('Owner','fixture@example.invalid','hashed',1,0,'totp','sealed',1,2))
        db.execute('INSERT INTO settings VALUES(?,?,1)',('smtp','sealed-smtp-and-webhook-fixture'))
        db.commit()
    cfg=definition();compose=root/'docker-compose.yaml';compose.write_text(json.dumps(cfg));(root/'.env').write_text('MCJ_GAME_MEMORY_MB=8192\n')
    items=containers(str(root));scope={'project':'actual_label_project','root':str(root),'compose':str(compose),'ids':{s:items[n]['Id'] for n,s in enumerate(update.SERVICES)},'images':{s:OLD for s in update.SERVICES}}
    operations=[];fail={'health':False,'up':False,'hash':False,'data':False}
    monkeypatch.setattr(update,'discover',lambda rows:scope)
    monkeypatch.setattr(update,'key_facts',lambda p,owner=(1009,10):{'encryption':'unchanged','rpc':'unchanged','rcon':'unchanged'})
    monkeypatch.setattr(update,'freeze_networks',lambda value,rows:copy.deepcopy(value))
    monkeypatch.setattr(update.os,'fchown',lambda *a:None,raising=False)
    if os.name=='nt':
        monkeypatch.setattr(update.os,'fchmod',lambda *a:None,raising=False)
        monkeypatch.setattr(update.os,'O_NOFOLLOW',0,raising=False)
        def portable_parent(root,owner):
            parent=root/'mcj_controller/.rollback';parent.mkdir(exist_ok=True);return parent
        monkeypatch.setattr(update,'rollback_parent',portable_parent)
    monkeypatch.setattr(update,'inspect',lambda name:next(x for x in items if name in (x['Id'],x['Name'].lstrip('/'))))
    def docker(*args,**kwargs):
        operations.append(args)
        if args[0] in ('start','stop'):
            targets=[x for x in items if x['Id'] in args[1:]]
            for x in targets:x['State']['Running']=args[0]=='start'
        return SimpleNamespace(stdout='')
    monkeypatch.setattr(update,'docker',docker)
    def invoke(image,sc,value,environment,action):
        operations.append(('compose',sc['project'],sc['compose'],action))
        if action=='hash':return '\n'.join(s+' '+('f'*64 if fail['hash'] else str(n+1)*64) for n,s in enumerate(update.SERVICES))
        if action=='up' and fail['up'] and value['services']['manager']['image']==NEW:raise ValueError('fixture_update_failure')
        for x in items[:2]:
            x['State']['Running']=action=='up';x['Image']=value['services'][x['Config']['Labels']['com.docker.compose.service']]['image']
        if action=='up' and fail['data'] and value['services']['manager']['image']==NEW:
            with closing(sqlite3.connect(dbpath)) as db:db.execute("UPDATE settings SET value='fixture-unexpected-change'");db.commit()
        return ''
    monkeypatch.setattr(update,'invoke',invoke)
    def healthy(image,*args):
        if fail['health'] and image==NEW:raise ValueError('update_health_failed')
        assert all(x['State']['Running'] and x['Image']==image for x in items[:2])
    monkeypatch.setattr(update,'healthy',healthy)
    return SimpleNamespace(root=root,state=state,database=dbpath,items=items,scope=scope,operations=operations,fail=fail)

def test_successful_update_preserves_game_credentials_and_verified_backup(lifecycle):
    x=lifecycle;game=copy.deepcopy(x.items[2]);report=update.work(x.scope,NEW)
    assert report['phase']=='complete' and report['credentials_preserved'] and report['game_unchanged']
    assert x.items[2]==game and not (x.state/'.deployment-hold.json').exists()
    backup=Path(report['rollback_folder'])/'manager.sqlite3'
    with sqlite3.connect(backup) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not any('minecraft' in str(op) for op in x.operations if op[0]!='compose')

@pytest.mark.parametrize('failure',['health','up','data'])
def test_failed_update_restores_database_and_old_images_without_game_restart(lifecycle,failure):
    x=lifecycle;x.fail[failure]=True;game=copy.deepcopy(x.items[2])
    with pytest.raises(ValueError):update.work(x.scope,NEW)
    assert all(v['Image']==OLD and v['State']['Running'] for v in x.items[:2])
    assert x.items[2]==game and not (x.state/'.deployment-hold.json').exists()
    with sqlite3.connect(x.database) as db:assert db.execute('SELECT value FROM settings').fetchone()[0]=='sealed-smtp-and-webhook-fixture'
    assert json.loads((x.state/'application-update.json').read_text())['phase']=='rolled_back'

def test_changed_compose_hash_stops_before_backup_or_service_stop(lifecycle):
    x=lifecycle;x.fail['hash']=True;before=x.database.read_bytes()
    with pytest.raises(ValueError,match='changed_since_deployment'):update.work(x.scope,NEW)
    assert x.database.read_bytes()==before and not list(x.root.glob('mcj_controller/.rollback/*'))
    assert not any(op[0]=='stop' for op in x.operations)

def test_active_maintenance_is_not_interrupted(lifecycle):
    x=lifecycle
    with closing(sqlite3.connect(x.database)) as db:db.execute("INSERT INTO jobs VALUES('running')");db.commit()
    with pytest.raises(ValueError,match='maintenance_busy'):update.work(x.scope,NEW)
    assert all(v['State']['Running'] for v in x.items) and not any(op[0]=='stop' for op in x.operations)

def test_repeat_current_image_validates_scope_but_does_not_restart_services(lifecycle):
    x=lifecycle;before=x.database.read_bytes()
    assert update.work(x.scope,OLD)['noop']
    assert x.database.read_bytes()==before and not any(op[0]=='stop' or op[-1]=='up' for op in x.operations)

def test_lost_lease_is_detected_before_stopping_the_manager(lifecycle,monkeypatch):
    x=lifecycle
    monkeypatch.setattr(update.Lease,'check',lambda *_:(_ for _ in ()).throw(ValueError('update_lease_lost')))
    with pytest.raises(ValueError,match='lease_lost'):update.work(x.scope,NEW)
    assert all(v['State']['Running'] for v in x.items) and not any(op[0]=='stop' for op in x.operations)

def test_selected_service_group_is_used_for_update_status_and_lease(lifecycle,monkeypatch):
    x=lifecycle;compose=Path(x.scope['compose']);cfg=json.loads(compose.read_text())
    for service in update.SERVICES:cfg['services'][service]['user']='245001:245001'
    compose.write_text(json.dumps(cfg));owners=[];writes=[]
    monkeypatch.setattr(update.os,'fchown',lambda fd,uid,gid:owners.append((uid,gid)),raising=False)
    original=update.atomic
    def observe(path,raw,mode=0o640,owner=(0,10)):
        writes.append((path.name,owner));return original(path,raw,mode,owner)
    monkeypatch.setattr(update,'atomic',observe)
    assert update.work(x.scope,NEW)['phase']=='complete'
    assert (0,245001) in owners
    assert all(owner==(0,245001) for name,owner in writes if name=='application-update.json')

@pytest.mark.skipif(os.name=='nt',reason='POSIX directory ownership and no-follow semantics')
def test_first_app_update_keeps_shared_rollback_parent_usable_by_service(lifecycle,monkeypatch):
    x=lifecycle;owners=[]
    def capture(fd,uid,gid):
        if stat.S_ISDIR(os.fstat(fd).st_mode):owners.append((uid,gid))
    monkeypatch.setattr(update.os,'fchown',capture,raising=False)
    report=update.work(x.scope,NEW)
    parent=x.root/'mcj_controller/.rollback'
    assert owners==[(1009,10)]
    assert Path(report['rollback_folder']).parent==parent
    if os.name!='nt':assert stat.S_IMODE(parent.stat().st_mode)==0o700

@pytest.mark.skipif(os.name=='nt',reason='POSIX directory ownership and no-follow semantics')
def test_existing_root_rollback_parent_is_migrated_without_changing_private_snapshots(tmp_path,monkeypatch):
    control=tmp_path/'mcj_controller';parent=control/'.rollback';private=parent/'ugos-app-prior'
    private.mkdir(parents=True,mode=0o700);snapshot=private/'manager.sqlite3';snapshot.write_bytes(b'private snapshot')
    snapshot.chmod(0o600);before=(private.stat().st_mode,snapshot.stat().st_mode,snapshot.read_bytes())
    owner=(os.getuid(),os.getgid());chowns=[]
    monkeypatch.setattr(update.os,'fchown',lambda fd,uid,gid:chowns.append((os.fstat(fd).st_ino,uid,gid)))
    assert update.rollback_parent(tmp_path,owner)==parent
    assert chowns==[(parent.stat().st_ino,*owner)]
    assert before==(private.stat().st_mode,snapshot.stat().st_mode,snapshot.read_bytes())

@pytest.mark.skipif(os.name=='nt',reason='POSIX directory no-follow semantics')
def test_symlinked_rollback_parent_is_refused_before_services_stop(lifecycle,tmp_path):
    x=lifecycle;outside=tmp_path/'outside';outside.mkdir()
    (x.root/'mcj_controller/.rollback').symlink_to(outside,target_is_directory=True)
    with pytest.raises((ValueError,OSError)):update.work(x.scope,NEW)
    assert not any(op[0]=='stop' for op in x.operations)
    assert not list(outside.iterdir())

@pytest.mark.skipif(os.name=='nt',reason='POSIX directory ownership and no-follow semantics')
def test_foreign_owned_rollback_parent_is_not_reassigned(tmp_path,monkeypatch):
    parent=tmp_path/'mcj_controller/.rollback';parent.mkdir(parents=True)
    real_stat=update.os.fstat;chowns=[]
    def foreign_owner(fd):
        info=real_stat(fd)
        return SimpleNamespace(st_uid=777777,st_gid=777777) if info.st_ino==parent.stat().st_ino else info
    monkeypatch.setattr(update.os,'fstat',foreign_owner)
    monkeypatch.setattr(update.os,'fchown',lambda *args:chowns.append(args))
    with pytest.raises(ValueError,match='update_rollback_owner_invalid'):update.rollback_parent(tmp_path,(245001,245001))
    assert not chowns

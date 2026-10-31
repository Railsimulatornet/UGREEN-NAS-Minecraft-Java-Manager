import concurrent.futures
import hashlib
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from mcj import job_control, player_presence, storage_admin
from test_security import environment, enroll, post



def test_connection_snapshot_corrects_logout_stale_journal_and_failures():
    original={'players':[{'name':'Traindriver316','online_since':100,'last_seen':200}]}
    assert player_presence.names('There are 0 of a max of 20 players online: ')==[]
    assert player_presence.names('There are 2 of a max of 20 players online: Traindriver316, Moritz')==['Traindriver316','Moritz']
    assert player_presence.reconcile(original,[],300)['players'][0]['online'] is False
    assert player_presence.reconcile(original,[],300)['players'][0]['online_since'] is None
    assert player_presence.reconcile(original,['Traindriver316'],300)['players'][0]['online'] is True
    assert player_presence.reconcile(original,None,300)['players'][0]['online'] is None
    assert player_presence.reconcile(original,None,300)['players'][0]['online_since'] is None
    with pytest.raises(ValueError):player_presence.names('There are 2 of a max of 20 players online: Traindriver316')


def test_duplicate_submission_is_atomic_and_distinct_operations_survive(environment):
    app,client,credentials,mail=environment;add=app.state.add_job
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids=list(pool.map(lambda _:add('backup',{'kind':'manual'},1,'idle_now'),range(16)))
    assert len(set(ids))==1
    assert add('server',{'operation':'start'},1)!=add('server',{'operation':'stop'},1)
    with app.state.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs WHERE kind='backup'").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM events WHERE event='job_queued'").fetchone()[0]==3


def test_direct_properties_submission_uses_no_version_plan_and_retains_security(environment):
    app,client,credentials,mail=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    current=st.get('server')
    result=post(client,'/api/jobs',{'kind':'server_settings','payload':{'changes':{'properties':{'view-distance':'12'}}},'mode':'idle_now'},csrf)
    assert result.status_code==200,result.text
    again=post(client,'/api/jobs',{'kind':'server_settings','payload':{'changes':{'properties':{'view-distance':'12'}}},'mode':'idle_now'},csrf)
    assert again.json()['id']==result.json()['id']
    with st.db() as db:
        row=dict(db.execute('SELECT * FROM jobs WHERE id=?',(result.json()['id'],)).fetchone())
        assert db.execute('SELECT COUNT(*) FROM version_plans').fetchone()[0]==0
    value=json.loads(row['payload']);assert value['configuration']['properties']['view-distance']=='12'
    assert value['configuration']['loader_version']==current['loader_version']
    assert st.get('server')==current  # queueing never changes the running game
    assert post(client,'/api/jobs',{'kind':'server_settings','payload':{'changes':{'properties':{'online-mode':'false'}}}},csrf).status_code==409
    assert post(client,'/api/jobs',{'kind':'server_settings','payload':{'changes':{'version':'1.20.1'}}},csrf).status_code==409
    assert post(client,'/api/jobs',{'kind':'server_settings','payload':{'changes':{'properties':{'view-distance':'10'}}}}).status_code==403


def test_historical_settings_job_title_is_based_on_original_plan(environment):
    app,client,credentials,mail=environment;enroll(environment);st=app.state.store;current=st.get('server')
    configuration={**current,'properties':{**current.get('properties',{}),'view-distance':'12'}}
    with st.db() as db:
        db.execute('INSERT INTO version_plans(id,created,configuration,report,state,based_on) VALUES(?,?,?,?,?,?)',('a'*32,time.time(),json.dumps(configuration),'{}','metadata_passed',json.dumps(current)))
    app.state.add_job('version_test',{'id':'a'*32},1)
    assert client.get('/api/jobs').json()[0]['purpose']=='settings'
    st.set('server',{**current,'version':'different'})
    assert client.get('/api/jobs').json()[0]['purpose']=='settings'


def test_berlin_schedule_is_explicit_and_dst_safe(monkeypatch):
    monkeypatch.setattr(job_control.time,'time',lambda:datetime(2026,10,25,17,tzinfo=ZoneInfo('Europe/Berlin')).timestamp())
    stamp=job_control.berlin_timestamp('2026-10-26T06:30')
    assert datetime.fromtimestamp(stamp,ZoneInfo('Europe/Berlin')).hour==6
    with pytest.raises(ValueError):job_control.berlin_timestamp('2026-10-25T02:30')
    with pytest.raises(ValueError):job_control.berlin_timestamp('2027-03-28T02:30')


def test_progress_tracks_real_phases_and_does_not_claim_success(environment):
    app,client,credentials,mail=environment;st=app.state.store;identifier=app.state.add_job('version_test',{'id':'a'*32},1)
    with st.db() as db:db.execute("UPDATE jobs SET state='running' WHERE id=?",(identifier,))
    with job_control.operation(st,identifier):
        job_control.phase('backup');job_control.phase('test_starting');job_control.phase('test_running')
    with st.db() as db:row=dict(db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone())
    result=json.loads(row['result']);assert row['state']=='running'
    assert [x['stage'] for x in result['phases']]==['preparing','backup','test_starting','test_running']


def test_client_pack_deletion_revokes_links_and_previews_current(environment,tmp_path):
    app,client,credentials,mail=environment;st=app.state.store;root=st.state/'client-packs';root.mkdir()
    with st.db() as db:
        for number,fp in [(1,'old'),(2,'current')]:
            identifier=str(number)*32;raw=b'test-pack-'+str(number).encode();(root/(identifier+'.mrpack')).write_bytes(raw)
            db.execute('INSERT INTO client_packs VALUES(?,?,?,?,?,?,?,?)',(identifier,number,time.time(),1,fp,hashlib.sha256(raw).hexdigest(),len(raw),'{}'))
        db.execute('INSERT INTO client_pack_links(id,pack_id,actor,created,expires,token_hash) VALUES(?,?,?,?,?,?)',('3'*32,'1'*32,1,time.time(),0,'hash'))
    preview=storage_admin.delete(st,root,'client_pack',['1'*32],1,current_fingerprint='current')
    assert preview['active_links']==1 and (root/('1'*32+'.mrpack')).exists()
    assert storage_admin.delete(st,root,'client_pack',['2'*32],1,current_fingerprint='current')['current_packs']==1
    with pytest.raises(ValueError,match='selection_changed'):storage_admin.delete(st,root,'client_pack',['1'*32],1,current_fingerprint='current',confirmation='wrong')
    result=storage_admin.delete(st,root,'client_pack',['1'*32],1,current_fingerprint='current',confirmation=preview['confirmation'])
    assert result['deleted'] and not (root/('1'*32+'.mrpack')).exists()
    with st.db() as db:
        assert db.execute('SELECT COUNT(*) FROM client_pack_links').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM client_packs').fetchone()[0]==1



def test_backup_bulk_delete_protects_last_available_archive_and_recovery_references(environment,tmp_path):
    app,client,credentials,mail=environment;st=app.state.store;root=tmp_path/'backups';root.mkdir()
    for number in range(1,5):
        identifier=str(number)*32;name='20261025T10000'+str(number)+'Z-'+str(number)*8+'.tar.gz';raw=b'owned-test-backup-'+str(number).encode()
        row={'id':identifier,'created':number,'kind':'manual','state':'verified','path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        (root/name).write_bytes(raw);(root/(name[:-7]+'.json')).write_text(json.dumps(row))
        with st.db() as db:db.execute('INSERT INTO backups(id,created,kind,state,path,size,sha256) VALUES(?,?,?,?,?,?,?)',tuple(row[k] for k in ['id','created','kind','state','path','size','sha256']))
    with pytest.raises(ValueError,match='protected'):storage_admin.delete(st,root,'backup',['4'*32],1)
    with pytest.raises(ValueError,match='protected'):storage_admin.delete(st,root,'backup',['1'*32,'4'*32],1)
    assert len(list(root.glob('*.tar.gz')))==4
    preview=storage_admin.delete(st,root,'backup',['1'*32,'2'*32],1)
    result=storage_admin.delete(st,root,'backup',['1'*32,'2'*32],1,confirmation=preview['confirmation'])
    assert result['deleted'] and len(list(root.glob('*.tar.gz')))==2
    with st.db() as db:
        assert db.execute('SELECT COUNT(*) FROM backups').fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM events WHERE event='backup_deleted'").fetchone()[0]==1
    # A queued restore protects the selected recovery archive too.
    app.state.add_job('restore',{'id':'3'*32},1)
    with pytest.raises(ValueError,match='protected'):storage_admin.delete(st,root,'backup',['3'*32],1)


def test_runtime_inventory_and_deletion_is_scoped_to_unused_owned_directories(environment,tmp_path):
    from mcj import runtime_storage
    app,client,credentials,mail=environment;st=app.state.store
    st.set('server',{**st.get('server'),'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.97'})
    for version in ['26.3.0.95','26.3.0.96','26.3.0.97']:
        folder=tmp_path/'server/libraries/net/neoforged/neoforge'/version;folder.mkdir(parents=True)
        (folder/('neoforge-'+version+'-universal.jar')).write_bytes(b'owned fixture jar')
    shared=tmp_path/'server/libraries/shared';shared.mkdir();(shared/'shared.jar').write_bytes(b'keep')
    rollback=tmp_path/'.rollback/previous/runtime';rollback.mkdir(parents=True);(rollback/'runtime.json').write_text(json.dumps({'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.96'}))
    values=runtime_storage.inventory(tmp_path,st.get('server'));assert {x['status'] for x in values}=={'active','rollback','unused'}
    unused=next(x for x in values if x['status']=='unused');active=next(x for x in values if x['status']=='active')
    with pytest.raises(ValueError,match='protected'):runtime_storage.delete(st,tmp_path,active['id'],1)
    preview=runtime_storage.delete(st,tmp_path,unused['id'],1)
    runtime_storage.delete(st,tmp_path,unused['id'],1,preview['confirmation'])
    assert (shared/'shared.jar').read_bytes()==b'keep'
    assert len(runtime_storage.inventory(tmp_path,st.get('server')))==2


def test_world_operations_are_queued_without_mutating_live_world(environment):
    app,client,credentials,mail=environment;csrf=enroll(environment)['csrf'];st=app.state.store;current=st.get('server')
    create=post(client,'/api/jobs',{'kind':'world_change','payload':{'name':'OwnedTestWorld','create':True,'generation':{'level-seed':'123','level-type':'minecraft:flat','generate-structures':'true'}},'mode':'idle_now'},csrf)
    assert create.status_code==200,create.text
    with st.db() as db:payload=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(create.json()['id'],)).fetchone()[0])
    assert payload['configuration']['world']=='OwnedTestWorld'
    assert payload['configuration']['loader_version']==current['loader_version']
    assert st.get('server')==current
    assert post(client,'/api/jobs',{'kind':'world_delete','payload':{'name':current.get('world','world')}},csrf).status_code==409
    assert post(client,'/api/jobs',{'kind':'world_change','payload':{'name':'../escape'}},csrf).status_code==409
    assert post(client,'/api/jobs',{'kind':'world_change','payload':{'name':'OwnedTestWorld','generation':{'online-mode':'false'}}},csrf).status_code==409

def test_legacy_pending_duplicates_collapsed_and_original_schedule_preserved(environment):
 app,_,_,_=environment;st=app.state.store
 with st.db() as db:
  for identifier,created,mode,payload,state in [('first',1,'manual','{}','planned'),('second',2,'idle_now','{}','queued'),('other',3,'idle_now','{"different":true}','queued'),('running',4,'idle_now','{}','running')]:
   db.execute('INSERT INTO jobs(id,kind,state,created,updated,actor,payload,mode,approved) VALUES(?,?,?,?,?,?,?,?,?)',(identifier,'mod_check',state,created,created,1,payload,mode,mode!='manual'))
 assert job_control.deduplicate_pending(st)==['second']
 assert job_control.deduplicate_pending(st)==[]
 with st.db() as db:
  assert db.execute('SELECT state FROM jobs WHERE id="first"').fetchone()[0]=='planned'
  assert db.execute('SELECT state FROM jobs WHERE id="running"').fetchone()[0]=='running'

def test_immediate_requires_explicit_confirmation_and_live_admin_job(environment):
 from mcj import maintenance
 from types import SimpleNamespace
 app,client,_,_=environment;csrf=enroll(environment)["csrf"];st=app.state.store
 data={'kind':'server','payload':{'operation':'restart'},'mode':'immediate','approved':True}
 assert post(client,'/api/jobs',data,csrf).status_code==409
 data['disconnect_confirmed']=True;response=post(client,'/api/jobs',data,csrf);assert response.status_code==200;identifier=response.json()['id']
 with job_control.operation(st,identifier):assert not job_control.may_disconnect_players()
 with st.db() as db:db.execute("UPDATE jobs SET state='running' WHERE id=?",(identifier,))
 with job_control.operation(st,identifier):assert job_control.may_disconnect_players()
 assert not job_control.may_disconnect_players()
 with st.db() as db:db.execute('UPDATE users SET enabled=0 WHERE id=1')
 with job_control.operation(st,identifier):assert not job_control.may_disconnect_players()

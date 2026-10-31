import hashlib,json,time
import pytest
from mcj import game_access
from test_security import environment,enroll,post

def report(root,public=True,fingerprint='legacy',protocol='mcj_network_v1',at=None):
    path=root/'control/reports/guard-status.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'at':time.time() if at is None else at,'network_access_protocol':protocol,'public_game':public,'network_access_fingerprint':fingerprint}))

def test_legacy_guard_never_claims_to_enforce_network_policy(environment):
    app,_,_,_=environment;root=app.state.store.state.parent
    report(root,protocol='old_guard');value=game_access.read(root,'container-a')
    assert value['public_game'] and not value['ready']
    with pytest.raises(ValueError,match='guard_update_required'):game_access.change(root,'container-a',False,value['basis'])
    assert not game_access.policy_path(root).exists()

def test_new_policy_requires_guard_ack_and_changed_container_invalidates_preview(environment,monkeypatch):
    app,_,_,_=environment;root=app.state.store.state.parent;report(root)
    current=game_access.read(root,'container-a')
    with pytest.raises(ValueError,match='game_access_changed'):game_access.change(root,'container-b',False,current['basis'])
    def acknowledge(_):
        raw=game_access.policy_path(root).read_bytes();report(root,json.loads(raw)['public_game'],hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(game_access.time,'sleep',acknowledge)
    result=game_access.change(root,'container-a',False,current['basis'])
    assert result['acknowledged'] and result['public_game'] is False and not result['restart_required']

def test_missing_ack_restores_exact_previous_policy_and_rejects_stale_heartbeat(environment,monkeypatch):
    app,_,_,_=environment;root=app.state.store.state.parent;report(root)
    current=game_access.read(root,'container-a');monkeypatch.setattr(game_access.time,'sleep',lambda _:None)
    with pytest.raises(ValueError,match='acknowledgement_missing'):game_access.change(root,'container-a',False,current['basis'])
    assert not game_access.policy_path(root).exists()
    report(root,at=time.time()-30);assert not game_access.read(root,'container-a')['ready']

def test_game_access_requires_admin_csrf_and_explicit_confirmation(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];calls=[]
    app.state.rpc=lambda path,payload=None:calls.append((path,payload)) or {'public_game':True,'ready':True,'basis':'b'*64}
    assert client.get('/api/infrastructure/game').json()['ready']
    assert post(client,'/api/infrastructure/game',{'public_game':False,'basis':'b'*64,'confirmed':True}).status_code==403
    assert post(client,'/api/infrastructure/game',{'public_game':False,'basis':'b'*64},csrf).status_code==409
    assert post(client,'/api/infrastructure/game',{'public_game':False,'basis':'b'*64,'confirmed':True},csrf).status_code==200
    assert calls[-1]==('/network-access',{'public_game':False,'basis':'b'*64})
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/infrastructure/game').status_code==403

def test_protection_update_is_bound_to_artifact_and_waits_for_idle_without_other_mods(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    app.state.rpc=lambda path,payload=None:{'update_available':True,'update_basis':'preview-basis','update_guard_sha256':'a'*64}
    assert post(client,'/api/infrastructure/game/update',{'basis':'stale'},csrf).status_code==409
    response=post(client,'/api/infrastructure/game/update',{'basis':'preview-basis'},csrf);assert response.status_code==200
    with st.db() as db:job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(response.json()['id'],)).fetchone())
    payload=json.loads(job['payload'])
    assert job['kind']=='server_settings' and job['mode']=='idle_5min' and job['state']=='queued'
    assert payload['configuration']==st.get('server') and payload['guard_sha256']=='a'*64 and payload['protection_update']
    assert not payload.get('include_pending_mods')

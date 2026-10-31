import hashlib,json,time
import pytest
from mcj import mods
from test_security import environment,enroll,post


def request(st):
    basis=hashlib.sha256(json.dumps(st.get('server'),sort_keys=True).encode()).hexdigest()
    return {'kind':'server_settings','mode':'idle_now','payload':{'changes':{'properties':{'view-distance':'12','simulation-distance':'6'}},'basis':basis,'include_pending_mods':True,'mod_fingerprint':mods.fingerprint(st)}}


def test_multiple_properties_and_reviewed_mods_are_one_idempotent_job_without_live_mutation(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;before=st.get('server')
    data=request(st);first=post(client,'/api/jobs',data,csrf);again=post(client,'/api/jobs',data,csrf)
    assert first.status_code==200 and first.json()['id']==again.json()['id']
    with st.db() as db:
        rows=db.execute('SELECT * FROM jobs').fetchall();assert len(rows)==1
        payload=json.loads(rows[0]['payload'])
        assert payload['configuration']['properties']['view-distance']=='12'
        assert payload['configuration']['properties']['simulation-distance']=='6'
        assert payload['include_pending_mods'] and payload['mod_fingerprint']==data['payload']['mod_fingerprint']
        assert db.execute('SELECT COUNT(*) FROM version_plans').fetchone()[0]==0
    assert st.get('server')==before
    assert client.get('/api/jobs').json()[0]['combined_changes'] is True


@pytest.mark.parametrize('change',['basis','fingerprint','boolean','protected','world','version'])
def test_stale_or_unsafe_combined_requests_never_enter_the_queue(environment,change):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;data=request(st);payload=data['payload']
    if change=='basis':payload['basis']='stale'
    if change=='fingerprint':payload['mod_fingerprint']='0'*64
    if change=='boolean':payload['include_pending_mods']='true'
    if change=='protected':payload['changes']['properties']['online-mode']='false'
    if change=='world':payload['changes']['properties']['level-name']='otherworld'
    if change=='version':payload['changes']['version']='1.21.1'
    assert post(client,'/api/jobs',data,csrf).status_code==409
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0


def test_pending_download_blocks_combined_job_and_csrf_admin_rules_remain(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    app.state.add_job('source_stage',{'id':'fixture-source'},1)
    assert post(client,'/api/jobs',request(st),csrf).status_code==409
    assert post(client,'/api/jobs',request(st)).status_code==403
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,'/api/jobs',request(st),csrf).status_code==403


def test_reviewed_fingerprint_is_not_silently_replaced_after_a_concurrent_change(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;data=request(st);reviewed=data['payload']['mod_fingerprint']
    calls=[]
    def changing(_):calls.append(1);return reviewed if len(calls)==1 else '1'*64
    monkeypatch.setattr(mods,'fingerprint',changing)
    response=post(client,'/api/jobs',data,csrf);assert response.status_code==200
    with st.db() as db:payload=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(response.json()['id'],)).fetchone()[0])
    assert payload['mod_fingerprint']==reviewed

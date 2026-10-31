import json
import pytest
from mcj.player_admission import opens_to_new_players,require_verified,view
from test_security import environment,enroll,post

@pytest.mark.parametrize('ready',[{}, {'ready':True,'visitor_verified':False}, {'ready':False,'visitor_verified':True}])
def test_new_admission_requires_both_artifact_client_proof_and_live_protection(ready):
    with pytest.raises(ValueError,match='verified_guard'):require_verified(ready)

def test_restricting_names_is_not_mistaken_for_opening_and_live_state_is_distinct():
    closed={'properties':{'white-list':'true'}};opened={'properties':{'white-list':'false'}}
    assert opens_to_new_players(closed,opened)
    assert not opens_to_new_players(opened,closed)
    assert not opens_to_new_players(opened,opened)
    state=view(opened,{'white-list':'true','online-mode':'true'},{'ready':True,'visitor_verified':True})
    assert state['configured_open'] and not state['open_to_new_players'] and state['can_open'] and state['online_mode']

def test_ordinary_settings_route_cannot_bypass_admission_protection(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    current=st.get('server');current['properties']['white-list']='true';st.set('server',current)
    app.state.rpc=lambda *args:{'ready':True,'visitor_verified':False}
    request={'kind':'server_settings','mode':'idle_5min','payload':{'changes':{'properties':{'white-list':'false'}}}}
    rejected=post(client,'/api/jobs',request,csrf)
    assert rejected.status_code==409 and rejected.json()['detail']=='visitor_admission_requires_verified_guard'
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
    app.state.rpc=lambda *args:{'ready':True,'visitor_verified':True,'guard_sha256':'a'*64}
    accepted=post(client,'/api/jobs',request,csrf)
    assert accepted.status_code==200
    with st.db() as db:job=dict(db.execute('SELECT * FROM jobs').fetchone())
    value=json.loads(job['payload'])
    assert value['configuration']['properties']['white-list']=='false'
    assert value['configuration']['properties']['online-mode']=='true' and not value.get('include_pending_mods')
    assert job['mode']=='idle_5min' and st.get('server')==current

def test_admission_status_requires_full_admin_session_and_reports_actual_properties(environment):
    app,client,_,_=environment
    assert client.get('/api/player-admission').status_code==401
    csrf=enroll(environment)['csrf']
    app.state.rpc=lambda path,payload=None:({'white-list':'true','online-mode':'true'} if path=='/properties' else {'ready':True,'visitor_verified':False})
    assert client.get('/api/player-admission').json()['can_open'] is False
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0')
    assert client.get('/api/player-admission').status_code==403

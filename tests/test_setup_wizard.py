import copy
import pytest
from test_security import environment,enroll,post,login

def test_existing_installation_is_not_marked_as_first_run(environment):
    app,client,_,_=environment;enroll(environment)
    assert client.get('/api/auth/me').json()['setup_wizard_pending'] is False
    value=client.get('/api/setup').json()
    assert value['step']==0 and not value['pending'] and not value['completed']
    assert app.state.store.get('setup_wizard') is None

def test_fresh_progress_resumes_and_completion_changes_no_access_or_runtime(environment):
    app,client,_,_=environment;st=app.state.store
    st.set('setup_wizard',{'enabled':True,'completed':False,'step':0})
    csrf=enroll(environment)['csrf']
    assert client.get('/api/auth/me').json()['setup_wizard_pending']
    keys=['server','release','web_access','smtp','maintenance']
    before={key:copy.deepcopy(st.get(key)) for key in keys}
    assert post(client,'/api/setup',{'step':2},csrf).json()['step']==2
    assert client.get('/api/setup').json()['step']==2
    assert post(client,'/api/setup',{'step':4,'complete':True},csrf).status_code==409
    assert post(client,'/api/setup',{'step':2,'complete':True,'reviewed':True},csrf).status_code==409
    assert post(client,'/api/setup',{'step':4,'complete':True,'reviewed':True},csrf).json()['completed']
    assert client.get('/api/auth/me').json()['setup_wizard_pending'] is False
    assert {key:st.get(key) for key in keys}==before
    with st.db() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE event='setup_wizard_completed'").fetchone()[0]==1
    assert post(client,'/api/setup',{'step':4,'complete':True,'reviewed':True},csrf).status_code==200
    with st.db() as db:assert db.execute("SELECT COUNT(*) FROM events WHERE event='setup_wizard_completed'").fetchone()[0]==1

def test_setup_requires_admin_mfa_and_csrf_and_never_returns_secrets(environment):
    app,client,_,_=environment;st=app.state.store
    assert client.get('/api/setup').status_code==401
    csrf=login(environment)
    assert client.get('/api/setup').status_code==403
    csrf=enroll(environment)['csrf']
    smtp=st.get('smtp');smtp.update(host='smtp.example.invalid',username='owner@example.invalid',sender='owner@example.invalid',password='never-return-this-fixture-secret')
    st.set('smtp',smtp,True)
    value=client.get('/api/setup')
    assert value.json()['mail_configured'] and 'never-return-this-fixture-secret' not in value.text
    assert 'owner@example.invalid' not in value.text and 'smtp.example.invalid' not in value.text
    assert post(client,'/api/setup',{'step':1}).status_code==403
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/setup').status_code==403
    assert post(client,'/api/setup',{'step':1},csrf).status_code==403

@pytest.mark.parametrize('value',[{'step':-1},{'step':5},{'step':True},{'step':'1'},{'step':0,'complete':'yes'},{'step':0,'external_web':True},{'step':0,'security_verified':True}])
def test_invalid_wizard_progress_is_rejected(environment,value):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    assert post(client,'/api/setup',value,csrf).status_code==422
    assert app.state.store.get('setup_wizard') is None

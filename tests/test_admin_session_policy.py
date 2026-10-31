import re,time
import pytest
from test_security import environment,enroll,post


def email_login(environment,name):
    app,client,credentials,mail=environment
    login=post(client,'/api/auth/login',{'username':name,'password':'A-Strong-Test-Password-2026!'})
    assert login.status_code==200 and login.json()['mfa_required']
    assert client.get('/api/auth/session-policy').status_code==403
    code=re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    result=post(client,'/api/auth/verify',{'code':code,'challenge':login.json()['challenge']},login.json()['csrf'])
    assert result.status_code==200
    return result.json()['csrf']


def test_each_admin_has_independent_preferences_and_new_login_requires_mfa(environment):
    app,client,credentials,mail=environment
    csrf=enroll(environment,method='email')['csrf']
    before=client.get('/api/auth/session-policy').json()
    assert before['policy']=={'absolute_seconds':43200,'idle_seconds':14400}
    assert post(client,'/api/auth/session-policy',{'absolute_hours':36,'idle_minutes':60},csrf).status_code==200
    after=client.get('/api/auth/session-policy').json()
    assert after['policy']=={'absolute_seconds':129600,'idle_seconds':3600}
    assert after['current_session']['absolute_expires']==before['current_session']['absolute_expires']
    assert after['current_session']['idle_seconds']==14400
    assert post(client,'/api/auth/logout',csrf=csrf).status_code==200
    csrf=email_login(environment,'Roman')
    assert client.get('/api/auth/session-policy').json()['current_session']['absolute_seconds']==129600
    assert client.get('/api/auth/me').json()['session']['idle_seconds']==3600
    assert post(client,'/api/auth/logout',csrf=csrf).status_code==200
    csrf=enroll(environment,name='Moritz',method='email')['csrf']
    assert client.get('/api/auth/session-policy').json()['policy']=={'absolute_seconds':43200,'idle_seconds':14400}
    assert post(client,'/api/auth/session-policy',{'absolute_hours':8,'idle_minutes':30},csrf).status_code==200
    assert app.state.store.get('admin_session_policy:1')['absolute_seconds']==129600
    assert app.state.store.get('admin_session_policy:2')['absolute_seconds']==28800


@pytest.mark.parametrize('payload',[{'absolute_hours':0,'idle_minutes':15},{'absolute_hours':169,'idle_minutes':15},{'absolute_hours':1,'idle_minutes':61},{'absolute_hours':12,'idle_minutes':0},{'absolute_hours':12,'idle_minutes':1441},{'absolute_hours':True,'idle_minutes':15}])
def test_invalid_limits_cannot_weaken_sessions(environment,payload):
    csrf=enroll(environment)['csrf'];client=environment[1]
    assert post(client,'/api/auth/session-policy',payload,csrf).status_code==422
    assert client.get('/api/auth/session-policy').json()['policy']=={'absolute_seconds':43200,'idle_seconds':14400}


def test_policy_requires_admin_csrf_and_cannot_set_another_users_preference(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    assert post(client,'/api/auth/session-policy',{'absolute_hours':24,'idle_minutes':60}).status_code==403
    # Unknown IDs are not a writable selector: the route always uses the authenticated owner.
    assert post(client,'/api/auth/session-policy',{'absolute_hours':24,'idle_minutes':60,'user_id':2},csrf).status_code==422
    assert app.state.store.get('admin_session_policy:2') is None
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/auth/session-policy').status_code==403
    assert post(client,'/api/auth/session-policy',{'absolute_hours':24,'idle_minutes':60},csrf).status_code==403


def test_custom_idle_and_absolute_expiry_are_enforced_server_side(environment):
    app,client,_,_=environment;csrf=enroll(environment,method='email')['csrf']
    assert post(client,'/api/auth/session-policy',{'absolute_hours':24,'idle_minutes':30},csrf).status_code==200
    post(client,'/api/auth/logout',csrf=csrf);csrf=email_login(environment,'Roman')
    with app.state.store.db() as db:db.execute('UPDATE sessions SET last_seen=?',(time.time()-1801,))
    assert client.get('/api/auth/me').status_code==401
    csrf=email_login(environment,'Roman')
    with app.state.store.db() as db:db.execute('UPDATE sessions SET created=?,expires=?,last_seen=?',(time.time()-86401,time.time()+1000,time.time()))
    assert client.get('/api/auth/me').status_code==401

"""Real session/authentication checks. All accounts, mail and actions are isolated fixtures."""
import json
import re
import time

import pyotp
import pytest

from mcj import auth
from mcj.store import Store
from test_security import environment, enroll, post


@pytest.mark.parametrize('name,method',[('Roman','email'),('Moritz','totp')])
def test_each_owner_logs_in_once_then_uses_admin_session(environment,name,method):
    app,client,credentials,mail=environment
    st=app.state.store
    enroll(environment,name,method)
    with st.db() as db:
        user=dict(db.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone())
    secret=st.open(user['totp']) if method=='totp' else None
    # Start a genuinely new login, which always removes the previous session assurance.
    old_cookie=client.cookies[auth.COOKIE]
    response=post(client,'/api/auth/login',{'username':name,'password':'A-Strong-Test-Password-2026!'})
    assert response.status_code==200 and response.json()['mfa_required']
    assert client.cookies[auth.COOKIE]!=old_cookie
    csrf=response.json()['csrf']
    assert not client.get('/api/auth/me').json()['mfa_verified']
    assert client.get('/api/settings').status_code==403
    assert post(client,'/api/jobs',{'kind':'backup'},csrf).status_code==403
    assert post(client,'/api/auth/activity',{},csrf).status_code==403
    with st.db() as db:
        assert not db.execute('SELECT 1 FROM sessions WHERE token=?',(st.digest(old_cookie),)).fetchone()
        if method=='totp':db.execute('UPDATE users SET totp_last=-1 WHERE id=?',(user['id'],))
    code=pyotp.TOTP(secret).now() if secret else re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    pending_cookie=client.cookies[auth.COOKIE]
    verified=post(client,'/api/auth/verify',{'code':code,'challenge':response.json().get('challenge','')},csrf)
    assert verified.status_code==200
    cookie=verified.headers['set-cookie'].lower()
    assert all(flag in cookie for flag in ['secure','httponly','samesite=strict','path=/'])
    assert client.cookies[auth.COOKIE]!=pending_cookie
    csrf=verified.json()['csrf']
    # Age assurance well past the former five-minute gate; keep recent user activity.
    with st.db() as db:db.execute('UPDATE sessions SET mfa=?',(time.time()-7200,))
    assert client.get('/api/auth/me').json()['mfa_verified']
    for path in ['/api/settings','/api/users','/api/events/export','/api/diagnostics']:
        assert client.get(path).status_code==200,path
    for operation in ['start','stop','restart']:
        assert post(client,'/api/jobs',{'kind':'server','payload':{'operation':operation}},csrf).status_code==200
    for kind in ['backup','mod_check','apply_mods']:
        assert post(client,'/api/jobs',{'kind':kind},csrf).status_code==200
    maintenance=st.get('maintenance')
    assert post(client,'/api/settings',{'section':'maintenance','value':maintenance},csrf).status_code==200
    assert post(client,'/api/users',{'username':'FixtureViewer','email':'fixture@example.invalid'},csrf).status_code==200
    assert post(client,'/api/auth/backup-codes',{},csrf).status_code==200
    # Re-verification cannot silently extend an already authenticated session.
    assert post(client,'/api/auth/verify',{'code':code},csrf).status_code==409
    if method=='email':assert post(client,'/api/auth/email-challenge',{},csrf).status_code==409
    assert post(client,'/api/jobs',{'kind':'backup'}).json()['detail']=='csrf_failed'
    assert post(client,'/api/jobs',{'kind':'backup'},csrf,origin='https://evil.invalid').status_code==403
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=?',(user['id'],))
    assert post(client,'/api/jobs',{'kind':'backup'},csrf).json()['detail']=='admin_required'
    with st.db() as db:db.execute('UPDATE users SET admin=1 WHERE id=?',(user['id'],))
    assert post(client,'/api/auth/logout',{},csrf).status_code==200
    assert not client.cookies
    client.cookies.set(auth.COOKIE,verified.cookies[auth.COOKIE])
    assert client.get('/api/settings').status_code==401
    client.cookies.clear()
    response=post(client,'/api/auth/login',{'username':name,'password':'A-Strong-Test-Password-2026!'})
    assert response.status_code==200 and response.json()['mfa_required']
    assert client.get('/api/settings').status_code==403


@pytest.mark.parametrize('expired',['absolute','idle','generation','disabled'])
def test_invalid_sessions_cannot_be_revived_by_activity(environment,expired):
    app,client,_,_=environment
    csrf=enroll(environment)['csrf'];st=app.state.store;token=st.digest(client.cookies[auth.COOKIE])
    with st.db() as db:
        if expired=='absolute':db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
        elif expired=='idle':db.execute('UPDATE sessions SET last_seen=?',(time.time()-auth.IDLE_SECONDS-1,))
        elif expired=='generation':db.execute('UPDATE users SET generation=generation+1')
        else:db.execute('UPDATE users SET enabled=0')
    assert post(client,'/api/auth/activity',{},csrf).status_code==401
    assert post(client,'/api/jobs',{'kind':'backup'},csrf).status_code==401
    with st.db() as db:assert not db.execute('SELECT 1 FROM sessions WHERE token=?',(token,)).fetchone()


def test_background_reads_do_not_reset_idle_and_activity_does_not_extend_absolute_limit(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    last=time.time()-1200
    with st.db() as db:
        db.execute('UPDATE sessions SET last_seen=?',(last,))
        expires=db.execute('SELECT expires FROM sessions').fetchone()[0]
    for path in ['/api/auth/me','/api/jobs','/api/events']:
        assert client.get(path).status_code==200
    with st.db() as db:assert db.execute('SELECT last_seen FROM sessions').fetchone()[0]==last
    assert post(client,'/api/auth/activity',{},csrf).status_code==200
    with st.db() as db:
        row=db.execute('SELECT * FROM sessions').fetchone()
        assert row['last_seen']>last and row['expires']==expires
    response=post(client,'/api/auth/password',{'current':'A-Strong-Test-Password-2026!','password':'Another-Strong-Test-Password-2026!'},csrf)
    assert response.status_code==200
    with st.db() as db:assert db.execute('SELECT expires FROM sessions').fetchone()[0]==expires


def test_existing_database_session_migration_preserves_deadlines_and_mfa(environment,tmp_path):
    app,client,_,_=environment;enroll(environment);st=app.state.store
    with st.db() as db:
        before=dict(db.execute('SELECT * FROM sessions').fetchone())
        db.execute('ALTER TABLE sessions DROP COLUMN last_seen')
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:Store(st.state,tmp_path/'encryption'),range(2)))
    with st.db() as db:
        after=dict(db.execute('SELECT * FROM sessions').fetchone())
        assert after['last_seen']==max(before['created'],before['mfa'])
        for key in ['token','created','expires','mfa','generation']:assert after[key]==before[key]
    assert client.get('/api/settings').status_code==200


def test_email_login_sends_once_and_concurrent_resends_reuse_challenge(environment):
    from concurrent.futures import ThreadPoolExecutor
    app,client,_,mail=environment;enroll(environment,'Roman','email');mail.clear()
    response=post(client,'/api/auth/login',{'username':'Roman','password':'A-Strong-Test-Password-2026!'})
    csrf=response.json()['csrf'];challenge=response.json()['challenge']
    assert len(mail)==1
    code=re.search(r'\b\d{6}\b',mail[0]['body'])[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda _:post(client,'/api/auth/email-challenge',{},csrf),range(2)))
    assert all(x.status_code==200 and x.json()['challenge']==challenge for x in replies)
    assert len(mail)==1
    assert post(client,'/api/auth/verify',{'code':code,'challenge':challenge},csrf).status_code==200


def test_email_resend_after_cooldown_replaces_previous_code(environment):
    app,client,_,mail=environment;enroll(environment,'Roman','email');mail.clear();st=app.state.store
    response=post(client,'/api/auth/login',{'username':'Roman','password':'A-Strong-Test-Password-2026!'})
    csrf=response.json()['csrf'];old=response.json()['challenge'];code=re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    with st.db() as db:db.execute('UPDATE challenges SET expires=expires-61 WHERE token=?',(st.digest(old),))
    resent=post(client,'/api/auth/email-challenge',{},csrf)
    assert resent.status_code==200 and resent.json()['challenge']!=old and len(mail)==2
    assert post(client,'/api/auth/verify',{'code':code,'challenge':old},csrf).status_code==401
    code=re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    assert post(client,'/api/auth/verify',{'code':code,'challenge':resent.json()['challenge']},csrf).status_code==200


def test_email_challenges_are_bound_to_individual_pending_login(environment):
    app,client,_,mail=environment;enroll(environment,'Roman','email');mail.clear()
    first=post(client,'/api/auth/login',{'username':'Roman','password':'A-Strong-Test-Password-2026!'}).json()
    code=re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    from fastapi.testclient import TestClient
    other=TestClient(app,base_url='https://testserver')
    second=post(other,'/api/auth/login',{'username':'Roman','password':'A-Strong-Test-Password-2026!'}).json()
    assert len(mail)==2 and first['challenge']!=second['challenge']
    assert post(other,'/api/auth/verify',{'code':code,'challenge':first['challenge']},second['csrf']).status_code==401
    assert post(client,'/api/auth/verify',{'code':code,'challenge':first['challenge']},first['csrf']).status_code==200

def test_realistic_owner_session_survives_three_idle_hours(environment):
 app,client,_,_=environment;enroll(environment);st=app.state.store
 with st.db() as db:db.execute('UPDATE sessions SET last_seen=?',(time.time()-3*3600,))
 assert client.get('/api/settings').status_code==200
 with st.db() as db:db.execute('UPDATE sessions SET last_seen=?',(time.time()-4*3600-1,))
 assert client.get('/api/settings').status_code==401


def test_twelve_hour_absolute_session_limit_still_enforced(environment):
 app,client,_,_=environment;enroll(environment);st=app.state.store;now=time.time()
 assert auth.SESSION_SECONDS==12*3600 and auth.IDLE_SECONDS==4*3600
 with st.db() as db:db.execute('UPDATE sessions SET created=?,expires=?,last_seen=?',(now-11*3600,now+3600,now))
 assert client.get('/api/settings').status_code==200
 with st.db() as db:db.execute('UPDATE sessions SET created=?',(now-12*3600-1,))
 assert client.get('/api/settings').status_code==401

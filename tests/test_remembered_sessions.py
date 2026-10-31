import re
import time
import pytest
from fastapi.testclient import TestClient
from mcj import auth
from test_security import environment, enroll, post


def remembered(environment,days=30,client=None,name='Roman'):
    app,original,_,mail=environment;client=client or original
    response=post(client,'/api/auth/login',{'username':name,'password':'A-Strong-Test-Password-2026!'})
    csrf=response.json()['csrf']
    code=re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    return post(client,'/api/auth/verify',{'code':code,'challenge':response.json()['challenge'],'remember_days':days},csrf)


def test_persistent_cookie_survives_browser_restart_and_only_hash_is_stored(environment):
    app,client,_,_=environment;enroll(environment,method='email')
    response=remembered(environment);assert response.status_code==200
    cookie=response.headers['set-cookie'].lower()
    assert all(flag in cookie for flag in ['__host-mcj=','secure','httponly','samesite=strict','path=/'])
    assert 'domain=' not in cookie
    assert re.search(r'max-age=(259199\d|2592000)',cookie)
    raw=client.cookies[auth.COOKIE]
    with app.state.store.db() as db:
        row=db.execute('SELECT * FROM sessions').fetchone()
        assert row['token']!=raw and row['token']==app.state.store.digest(raw)
        assert row['remember_days']==30 and row['absolute_seconds']==30*86400 and row['idle_seconds']==7*86400
    restarted=TestClient(app,base_url='https://testserver');restarted.cookies.set(auth.COOKIE,raw)
    assert restarted.get('/api/settings').status_code==200
    csrf=restarted.get('/api/auth/me').json()['csrf']
    assert post(restarted,'/api/auth/logout',csrf=csrf).status_code==200
    assert client.get('/api/auth/me').status_code==401


@pytest.mark.parametrize('days',[-1,31,True,'30',1.5])
def test_invalid_remember_duration_and_pending_session_never_grant_access(environment,days):
    _,client,_,mail=environment;enroll(environment,method='email')
    response=remembered(environment,days)
    assert response.status_code==422
    assert client.get('/api/settings').status_code==403


@pytest.mark.parametrize('expiry',['idle','absolute','disabled','generation'])
def test_remembered_sessions_enforce_expiration_and_revocation(environment,expiry):
    app,client,_,_=environment;enroll(environment,method='email');response=remembered(environment)
    with app.state.store.db() as db:
        if expiry=='idle':db.execute('UPDATE sessions SET last_seen=?',(time.time()-7*86400-1,))
        elif expiry=='absolute':db.execute('UPDATE sessions SET created=?',(time.time()-30*86400-1,))
        elif expiry=='disabled':db.execute('UPDATE users SET enabled=0 WHERE id=1')
        else:db.execute('UPDATE users SET generation=generation+1 WHERE id=1')
    assert client.get('/api/settings').status_code==401
    assert post(client,'/api/auth/activity',csrf=response.json()['csrf']).status_code==401


@pytest.mark.parametrize('age',[43201,7*86400,29*86400])
def test_valid_remembered_session_can_change_settings_without_another_factor(environment,age):
    app,client,_,mail=environment;enroll(environment,method='email');response=remembered(environment);csrf=response.json()['csrf']
    with app.state.store.db() as db:
        db.execute('UPDATE sessions SET created=?,mfa=?,last_seen=?',(time.time()-age,time.time()-age,time.time()-600))
        before=dict(db.execute('SELECT * FROM sessions').fetchone())
    sent=len(mail)
    assert post(client,'/api/auth/session-policy',{'absolute_hours':24,'idle_minutes':60},csrf).status_code==200
    with app.state.store.db() as db:after=dict(db.execute('SELECT * FROM sessions').fetchone())
    assert after['expires']==before['expires'] and after['created']==before['created'] and after['mfa']==before['mfa']
    assert len(mail)==sent


def test_optional_manual_reauth_does_not_extend_session_lifetime(environment):
    app,client,_,mail=environment;enroll(environment,method='email');response=remembered(environment);csrf=response.json()['csrf']
    with app.state.store.db() as db:
        db.execute('UPDATE sessions SET mfa=?,last_seen=?',(time.time()-43201,time.time()-600))
        row=dict(db.execute('SELECT * FROM sessions').fetchone())
    assert client.get('/api/settings').status_code==200
    assert post(client,'/api/auth/session-policy',{'absolute_hours':24,'idle_minutes':60},csrf).status_code==200
    context=post(client,'/api/auth/reauth/challenge',{},csrf).json()
    code=re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    assert post(client,'/api/auth/reauth',{'code':code,'challenge':context['challenge']}).status_code==403
    assert post(client,'/api/auth/reauth',{'code':'wrong','challenge':context['challenge']},csrf).status_code==401
    assert post(client,'/api/auth/reauth',{'code':code,'challenge':context['challenge']},csrf).status_code==200
    assert post(client,'/api/auth/reauth',{'code':code,'challenge':context['challenge']},csrf).status_code==401
    assert post(client,'/api/auth/session-policy',{'absolute_hours':24,'idle_minutes':60},csrf).status_code==200
    with app.state.store.db() as db:
        current=dict(db.execute('SELECT * FROM sessions').fetchone())
    assert current['expires']==row['expires'] and current['created']==row['created'] and current['mfa']>row['mfa']


def test_a_new_browser_still_requires_login_mfa(environment):
    app,client,_,_=environment;enroll(environment,method='email');remembered(environment)
    other=TestClient(app,base_url='https://testserver')
    assert other.get('/api/settings').status_code==401
    response=post(other,'/api/auth/login',{'username':'Roman','password':'A-Strong-Test-Password-2026!'})
    assert response.status_code==200
    assert other.get('/api/settings').status_code==403


def test_session_list_and_revocation_are_owner_scoped(environment):
    app,client,_,_=environment;enroll(environment,method='email');remembered(environment)
    other=TestClient(app,base_url='https://testserver');remembered(environment,14,other)
    rows=client.get('/api/auth/sessions').json();assert len(rows)==2 and sum(row['current'] for row in rows)==1
    assert all('token' not in row and 'ip' not in row for row in rows)
    old_id=next(row['id'] for row in rows if not row['current'])
    assert post(client,'/api/auth/sessions/revoke',{'identifier':old_id}).status_code==403
    csrf=client.get('/api/auth/me').json()['csrf']
    assert post(client,'/api/auth/sessions/revoke',{'identifier':old_id},csrf).status_code==200
    assert other.get('/api/auth/me').status_code==401
    # A different user cannot discover or revoke another owner's session.
    enroll(environment,name='Moritz',method='email');remembered(environment,name='Moritz')
    csrf=client.get('/api/auth/me').json()['csrf']
    assert len(client.get('/api/auth/sessions').json())==1
    assert post(client,'/api/auth/sessions/revoke',{'identifier':rows[0]['id']},csrf).status_code==404


def test_reauth_email_is_bound_to_session_and_password_change_revokes_other_devices(environment):
    app,client,_,mail=environment;enroll(environment,method='email');remembered(environment)
    other=TestClient(app,base_url='https://testserver');remembered(environment,14,other)
    csrf=client.get('/api/auth/me').json()['csrf'];other_csrf=other.get('/api/auth/me').json()['csrf']
    context=post(client,'/api/auth/reauth/challenge',{},csrf).json();code=re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    assert post(other,'/api/auth/reauth',{'code':code,'challenge':context['challenge']},other_csrf).status_code==401
    response=post(client,'/api/auth/password',{'current':'A-Strong-Test-Password-2026!','password':'Another-Strong-Test-Password-2026!'},csrf)
    assert response.status_code==200
    assert other.get('/api/auth/me').status_code==401
    with app.state.store.db() as db:assert db.execute('SELECT remember_days FROM sessions').fetchone()[0]==30

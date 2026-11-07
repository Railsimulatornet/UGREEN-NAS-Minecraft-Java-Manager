import io,json,re,sys,time,zipfile
from pathlib import Path
from mcj import __version__
from cryptography.fernet import Fernet
import pyotp
import pytest
from fastapi.testclient import TestClient
from mcj.web import create_app
from mcj.store import Store
from mcj import auth,mods,notify

@pytest.fixture
def environment(tmp_path,monkeypatch):
    root=tmp_path/'project'
    for name in ['state','staging','mods','control/roles']:(root/name).mkdir(parents=True,exist_ok=True)
    key=tmp_path/'encryption';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    onboarding=tmp_path/'bootstrap'
    monkeypatch.setenv('BOOTSTRAP_FILE',str(onboarding))
    Store(root/'state',key,onboarding,initial_accounts=[{'username':'Roman','email':'roman@example.invalid'},{'username':'Moritz','email':'moritz@example.invalid'}])
    app=create_app(root=root,keyfile=key,origin='https://testserver',start_worker=False)
    credentials=json.loads(app.state.store.cipher.decrypt(onboarding.read_bytes()))
    mail=[]
    def capture(st,recipient,subject,body,actor=None):mail.append({'recipient':recipient,'subject':subject,'body':body});return {'status':'smtp_accepted'}
    monkeypatch.setattr(auth,'send_email',capture)
    client=TestClient(app,base_url='https://testserver')
    return app,client,credentials,mail

def post(client,path,data=None,csrf=None,origin='https://testserver'):
    headers={'Origin':origin}
    if csrf:headers['X-CSRF-Token']=csrf
    return client.post(path,json=data or {},headers=headers)

def login(environment,name='Roman'):
    app,client,creds,mail=environment
    response=post(client,'/api/auth/login',{'username':name,'password':creds[name]['password']})
    assert response.status_code==200
    return response.json()['csrf']

def enroll(environment,name='Roman',method='totp'):
    app,client,creds,mail=environment;csrf=login(environment,name)
    response=post(client,'/api/auth/password',{'current':creds[name]['password'],'password':'A-Strong-Test-Password-2026!'},csrf)
    assert response.status_code==200;csrf=response.json()['csrf']
    if method=='email':configure_mail(environment)
    response=post(client,'/api/auth/setup/'+method,csrf=csrf)
    assert response.status_code==200
    challenge=response.json()
    code=pyotp.TOTP(challenge['secret']).now() if method=='totp' else re.search(r'\b\d{6}\b',mail[-1]['body'])[0]
    response=post(client,'/api/auth/setup/confirm',{'method':method,'challenge':challenge['challenge'],'code':code},csrf)
    assert response.status_code==200
    return response.json()

def configure_mail(environment):
    # Legacy email-factor tests model an installation with outgoing mail configured.
    # Fresh, empty-SMTP enrollment is exercised through real TLS in test_email_first_setup.
    st=environment[0].state.store
    if not st.get('smtp')['host']:
        st.set('smtp',{'host':'smtp.example.invalid','port':587,'security':'starttls',
                      'username':'fixture@example.invalid','sender':'fixture@example.invalid',
                      'password':'disposable-test-mail-password'},True)

def test_exact_initial_admins_and_argon2(environment):
    app,client,creds,mail=environment
    with app.state.store.db() as db:users=[dict(x) for x in db.execute('SELECT * FROM users')]
    assert [(x['username'],x['email'],x['admin'],x['force_password']) for x in users]==[
        ('Roman','roman@example.invalid',1,1),('Moritz','moritz@example.invalid',1,1)]
    assert all(x['password'].startswith('$argon2id$') for x in users)
    assert creds['Roman']['password']!=creds['Moritz']['password']


def test_health_reports_configured_release_state_without_account_information(environment):
    app,client,creds,mail=environment
    assert client.get('/healthz').json()['state']=='internal_validation'
    app.state.store.set('release',{'status':'public_preview','public_web':True,'public_game':False})
    value=client.get('/healthz').json()
    assert value=={'version':__version__,'state':'public_preview'}


def test_german_mail_survives_smtp_encoding(environment,monkeypatch):
    from email import policy
    from email.parser import BytesParser
    app,client,creds,mail=environment
    transmitted=[]
    class SMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):return 250,b'ok'
        def starttls(self,**kwargs):return 220,b'ready'
        def login(self,*args):return 235,b'ok'
        def send_message(self,message):
            transmitted.append(message.as_bytes(policy=policy.SMTP));return {}
    monkeypatch.setattr(notify.smtplib,'SMTP',SMTP)
    subject='MCJ Manager – Prüfung für Änderungen'
    body='Verschlüsselte Übertragung. Grüße für Roman und Moritz: ä ö ü Ä Ö Ü ß.'
    notify.send_email(app.state.store,'roman@example.invalid',subject,body)
    decoded=BytesParser(policy=policy.default).parsebytes(transmitted[0])
    assert decoded['Subject']==subject
    assert decoded.get_content().strip()==body
    assert decoded.get_content_charset()=='utf-8'

def test_unauthenticated_boundaries(environment):
    app,client,creds,mail=environment
    for path in ['/api/overview','/api/settings','/api/users','/api/diagnostics','/api/mods','/api/mods/test-results','/api/backups','/api/jobs','/api/players/permissions']:
        assert client.get(path).status_code==401
    assert post(client,'/api/register',{}).status_code in [403,404]


def test_role_permission_changes_require_mfa_csrf_and_safe_visitor_permissions(environment):
    from mcj.role_permissions import defaults
    app,client,creds,mail=environment;csrf=login(environment)
    assert post(client,'/api/players/permissions',{'roles':defaults()},csrf).status_code==403
    result=enroll(environment)
    assert post(client,'/api/players/permissions',{'roles':defaults()}).status_code==403
    assert post(client,'/api/players/permissions',{'roles':{**defaults(),'visitor':['kick']}},result['csrf']).status_code==409


def test_backup_history_and_restore_actions_follow_real_archive_state(environment,tmp_path,monkeypatch):
    import hashlib
    app,client,creds,mail=environment;csrf=enroll(environment)['csrf']
    app.state.rpc=lambda path,payload=None:{'protected_ids':[]} if path=='/backup/protection' else None
    monkeypatch.setenv('BACKUP_ROOT',str(tmp_path))
    identifier='a'*32;name='20261024T220000Z-12345678.tar.gz';raw=b'test archive'
    row={'path':name,'state':'verified','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    (tmp_path/name).write_bytes(raw);metadata=tmp_path/(name[:-7]+'.json');metadata.write_text(json.dumps(row))
    with app.state.store.db() as db:db.execute('INSERT INTO backups(id,created,kind,state,path,size,sha256) VALUES(?,?,?,?,?,?,?)',
        (identifier,time.time(),'manual','verified',name,len(raw),row['sha256']))
    assert client.get('/api/backups/history').json()['records'][0]['archive_available']
    assert client.get('/api/backups/'+identifier+'/download').content==raw
    assert post(client,'/api/jobs',{'kind':'restore','payload':{'id':identifier}},csrf).status_code==409
    (tmp_path/name).unlink();metadata.write_text(json.dumps({**row,'archive_state':'expired'}))
    record=client.get('/api/backups/history').json()['records'][0]
    assert record['state']=='verified' and record['archive_state']=='expired' and not record['archive_available']
    assert client.get('/api/backups/'+identifier+'/download').status_code==404
    for kind in ['restore','restore_test']:
        assert post(client,'/api/jobs',{'kind':kind,'payload':{'id':identifier,'confirmation':'restore '+identifier}},csrf).status_code==404
    assert client.get('/api/backups/history?cursor=invalid').status_code==400
    assert client.get('/api/backups/history?limit=2001').status_code==400

def test_headers_and_cookie(environment):
    app,client,creds,mail=environment
    response=client.get('/')
    assert response.headers['x-frame-options']=='DENY'
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert response.headers['cache-control']=='no-store'
    response=post(client,'/api/auth/login',{'username':'Roman','password':creds['Roman']['password']})
    cookie=response.headers['set-cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    assert '__Host-mcj=' in cookie and 'Domain=' not in cookie

def test_origin_host_and_csrf(environment):
    app,client,creds,mail=environment
    assert post(client,'/api/auth/login',{'username':'Roman','password':creds['Roman']['password']},origin='https://evil.invalid').status_code==403
    assert client.get('/',headers={'Host':'evil.invalid'}).status_code==400
    login(environment)
    assert post(client,'/api/auth/setup/totp').status_code==403

def test_first_login_cannot_skip_password_or_factor(environment):
    app,client,creds,mail=environment;csrf=login(environment)
    assert client.get('/api/overview').status_code==403
    assert post(client,'/api/auth/setup/totp',csrf=csrf).status_code==403

def test_totp_and_one_time_recovery(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    assert len(result['backup_codes'])==10
    assert client.get('/api/overview').status_code==200
    with app.state.store.db() as db:
        user=dict(db.execute("SELECT * FROM users WHERE username='Roman'").fetchone())
        hashes=[x[0] for x in db.execute('SELECT hash FROM recovery_codes WHERE user_id=?',(user['id'],))]
    assert not user['totp'].startswith('otpauth:')
    assert all(code not in hashes for code in result['backup_codes'])
    assert app.state.store.consume_recovery(user['id'],result['backup_codes'][0])
    assert not app.state.store.consume_recovery(user['id'],result['backup_codes'][0])

def test_email_factor_is_independent(environment):
    app,client,creds,mail=environment;result=enroll(environment,'Moritz','email')
    assert client.get('/api/auth/me').json()['user']['factor']=='email'
    assert client.get('/api/overview').status_code==200
    assert mail[-1]['recipient']=='moritz@example.invalid'
    with app.state.store.db() as db:
        user=db.execute("SELECT * FROM users WHERE username='Moritz'").fetchone()
        assert user['totp'] is None
    assert len(result['backup_codes'])==10

def test_totp_replay_is_rejected(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    user=client.get('/api/auth/me').json()['user']
    with app.state.store.db() as db:row=dict(db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone())
    code=pyotp.TOTP(app.state.store.open(row['totp'])).now()
    assert not auth.verify_factor(app.state.store,row,code)

def test_email_code_attempt_limit_and_single_use(environment):
    app,client,creds,mail=environment
    user={'id':1,'email':'roman@example.invalid','language':'de'}
    token=auth.challenge(app.state.store,1,'login',code='123456')
    for _ in range(5):assert not auth.consume_email(app.state.store,1,token,'000000','login')
    assert not auth.consume_email(app.state.store,1,token,'123456','login')
    token=auth.challenge(app.state.store,1,'login',code='123456')
    assert auth.consume_email(app.state.store,1,token,'123456','login')
    assert not auth.consume_email(app.state.store,1,token,'123456','login')

def test_reset_does_not_bypass_factor_and_invalidates_sessions(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    response=post(client,'/api/auth/forgot',{'email':'roman@example.invalid'})
    assert response.status_code==200
    token=mail[-1]['body'].split('#reset=')[1].strip()
    data={'token':token,'password':'Another-Safe-Test-Password-2026!'}
    assert post(client,'/api/auth/reset',data).status_code==401
    data.update(code=result['backup_codes'][0],recovery=True)
    assert post(client,'/api/auth/reset',data).status_code==200
    assert client.get('/api/overview').status_code==401
    assert post(client,'/api/auth/reset',data).status_code==400

def test_forgot_does_not_enumerate(environment):
    app,client,creds,mail=environment
    known=post(client,'/api/auth/forgot',{'email':'roman@example.invalid'})
    unknown=post(client,'/api/auth/forgot',{'email':'nobody@example.invalid'})
    assert known.status_code==unknown.status_code==200
    assert known.json()==unknown.json()


def test_first_setup_link_context_needs_no_factor_and_remains_single_use(environment):
    app,client,creds,mail=environment
    post(client,'/api/auth/forgot',{'email':'roman@example.invalid'})
    token=mail[-1]['body'].split('#reset=')[1].strip()
    context=post(client,'/api/auth/reset/context',{'token':token})
    assert context.status_code==200
    assert set(context.json())=={'username','factor','initial_setup','expires_at'}
    assert context.json()['username']=='Roman' and context.json()['factor'] is None and context.json()['initial_setup']
    assert post(client,'/api/auth/reset',{'token':token,'password':'First-Setup-Safe-Password-2026!'}).status_code==200
    assert post(client,'/api/auth/reset/context',{'token':token}).status_code==400
    assert post(client,'/api/auth/reset',{'token':token,'password':'First-Setup-Safe-Password-2026!'}).status_code==400
    assert post(client,'/api/auth/login',{'username':'Roman','password':'First-Setup-Safe-Password-2026!'}).status_code==200
    assert client.get('/api/settings').status_code==403


@pytest.mark.parametrize('method',['totp','email'])
def test_reset_context_preserves_existing_factor_requirement(environment,method):
    app,client,creds,mail=environment;enroll(environment,method=method)
    post(client,'/api/auth/forgot',{'email':'roman@example.invalid'})
    token=mail[-1]['body'].split('#reset=')[1].strip()
    context=post(client,'/api/auth/reset/context',{'token':token}).json()
    assert context['factor']==method and not context['initial_setup']
    assert post(client,'/api/auth/reset',{'token':token,'password':'Another-Safe-Test-Password-2026!'}).status_code==401
    assert post(client,'/api/auth/reset/context',{'token':token}).status_code==200


def test_expired_reset_context_is_rejected_and_does_not_change_password(environment):
    app,client,creds,mail=environment
    post(client,'/api/auth/forgot',{'email':'roman@example.invalid'})
    token=mail[-1]['body'].split('#reset=')[1].strip()
    with app.state.store.db() as db:db.execute('UPDATE challenges SET expires=? WHERE kind=?',(time.time()-1,'reset'))
    assert post(client,'/api/auth/reset/context',{'token':token}).status_code==400
    assert post(client,'/api/auth/login',{'username':'Roman','password':creds['Roman']['password']}).status_code==200


def test_reset_context_rejects_foreign_origin(environment):
    app,client,creds,mail=environment
    post(client,'/api/auth/forgot',{'email':'roman@example.invalid'})
    token=mail[-1]['body'].split('#reset=')[1].strip()
    assert post(client,'/api/auth/reset/context',{'token':token},origin='https://foreign.invalid').status_code==403

def test_login_rate_limit(environment):
    app,client,creds,mail=environment
    for i in range(8):assert post(client,'/api/auth/login',{'username':'Roman','password':'wrong'}).status_code==401
    assert post(client,'/api/auth/login',{'username':'Roman','password':creds['Roman']['password']}).status_code==429

def test_factor_remains_valid_for_authenticated_session(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    with app.state.store.db() as db:db.execute('UPDATE sessions SET mfa=?',(time.time()-301,))
    response=post(client,'/api/jobs',{'kind':'backup'},result['csrf'])
    assert response.status_code==200

def test_viewer_cannot_administer(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    with app.state.store.db() as db:db.execute("UPDATE users SET admin=0 WHERE username='Roman'")
    assert client.get('/api/overview').status_code==200
    assert client.get('/api/settings').status_code==403
    assert post(client,'/api/jobs',{'kind':'backup'},result['csrf']).status_code==403
    assert post(client,'/api/users',{'username':'New','email':'new@example.invalid'},result['csrf']).status_code==403


def test_viewer_status_and_history_exclude_every_configuration_copy(environment):
    app,client,creds,mail=environment;enroll(environment);st=app.state.store
    server=st.get('server');secret='CUSTOM-PROPERTY-FIXTURE-DO-NOT-USE'
    server['properties']={**server.get('properties',{}),'custom-mod-token':secret,'text-filtering-config':json.dumps({'apiKey':secret})}
    st.set('server',server);now=time.time();serialized=json.dumps(server)
    with st.db() as db:
        db.execute('INSERT INTO version_plans(id,created,actor,configuration,report,state,based_on,mod_fingerprint,test_result) VALUES(?,?,?,?,?,?,?,?,?)',
            ('a'*32,now,1,serialized,json.dumps({'configuration':server,'metadata_checks':'passed'}),'tested',serialized,'fixture',json.dumps({'runtime':server})))
        db.execute('INSERT INTO jobs(id,kind,state,created,updated,actor,mode,payload,result,approved) VALUES(?,?,?,?,?,?,?,?,?,1)',
            ('b'*32,'server_settings','succeeded',now,now,1,'manual',json.dumps({'configuration':server,'based_on':serialized}),json.dumps({'runtime':server,'started':now-2,'progress':'test_running','reason':secret})))
    for endpoint in ['/api/overview','/api/versions','/api/jobs']:
        response=client.get(endpoint);assert response.status_code==200 and secret in response.text
    with st.db() as db:db.execute("UPDATE users SET admin=0 WHERE username='Roman'")
    for endpoint in ['/api/overview','/api/versions','/api/jobs','/api/jobs?summary=true']:
        response=client.get(endpoint);assert response.status_code==200 and secret not in response.text
        assert 'custom-mod-token' not in response.text and 'based_on' not in response.text
    assert client.get('/api/overview').json()['server']['version']==server['version']
    plan=client.get('/api/versions').json()['plans'][0]
    assert plan['configuration']['loader']==server['loader'] and plan['report']['metadata_checks']=='passed'
    job=client.get('/api/jobs').json()[0]
    assert json.loads(job['result'])['progress']=='test_running'
    assert json.loads(job['result'])['runtime']['version']==server['version']
    assert json.loads(job['result'])['reason']=='job_failed'
    assert st.get('server')['properties']['custom-mod-token']==secret

def test_secrets_encrypted_and_absent_from_diagnostics(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    cfg=app.state.store.get('smtp');cfg['password']='TEST-SMTP-SECRET-DO-NOT-USE';app.state.store.set('smtp',cfg,True)
    with app.state.store.db() as db:
        text='\n'.join(db.iterdump())
    assert cfg['password'] not in text
    response=client.get('/api/settings');assert cfg['password'] not in response.text
    response=client.get('/api/diagnostics');assert cfg['password'] not in response.text
    assert 'totp' not in response.text

def test_diagnostics_excludes_arbitrary_property_credentials_without_changing_configuration(environment):
    app,client,creds,mail=environment;enroll(environment)
    server=app.state.store.get('server');server['properties']={**server.get('properties',{}),
        'text-filtering-config':'{"apiKey":"PRIVATE-FILTER-TOKEN"}',
        'custom-mod-token':'PRIVATE-MOD-TOKEN','management-server-tls-keystore-password':'PRIVATE-KEYSTORE-PASSWORD'}
    app.state.store.set('server',server)
    with app.state.store.db() as db:before=db.execute("SELECT value FROM settings WHERE name='server'").fetchone()[0]
    response=client.get('/api/diagnostics');assert response.status_code==200
    for secret in ['PRIVATE-FILTER-TOKEN','PRIVATE-MOD-TOKEN','PRIVATE-KEYSTORE-PASSWORD']:assert secret not in response.text
    assert 'properties' not in response.json()['server']
    with app.state.store.db() as db:assert db.execute("SELECT value FROM settings WHERE name='server'").fetchone()[0]==before

def test_smtp_destination_change_requires_new_secret(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    app.state.store.set('smtp',{'host':'smtp.example.invalid','port':587,'security':'starttls','username':'owner@example.invalid','sender':'owner@example.invalid','password':'owned-fixture-secret'},True)
    cfg=app.state.store.get('smtp');cfg.update(host='attacker.example',password='')
    response=post(client,'/api/settings',{'section':'smtp','value':cfg},result['csrf'])
    assert response.status_code==400
    assert app.state.store.get('smtp')['host']=='smtp.example.invalid'
    assert app.state.store.get('smtp')['password']=='owned-fixture-secret'

def test_no_unverified_automatic_maintenance(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    cfg=app.state.store.get('maintenance');cfg['automatic']=True
    assert post(client,'/api/settings',{'section':'maintenance','value':cfg},result['csrf']).status_code==409
    response=post(client,'/api/jobs',{'kind':'apply_mods','payload':{}},result['csrf'])
    assert response.status_code==200
    with app.state.store.db() as db:job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(response.json()['id'],)).fetchone())
    assert job['state']=='queued' and job['approved']==1
    assert app.state.store.get('release')['public_game'] is False


def second_account(environment,method='email'):
    app,client,credentials,mail=environment
    second=TestClient(app,base_url='https://testserver')
    result=enroll((app,second,credentials,mail),'Moritz',method)
    return second,result


def test_admin_edit_revokes_target_sessions_and_preserves_password_and_factor(environment):
    app,client,credentials,mail=environment;roman=enroll(environment)
    other,_=second_account(environment)
    st=app.state.store
    with st.db() as db:before=dict(db.execute("SELECT * FROM users WHERE username='Moritz'").fetchone())
    data={key:before[key] for key in ['username','email','admin','language','enabled']};data.update(enabled=False,language='en')
    result=post(client,'/api/users/'+str(before['id']),data,roman['csrf'])
    assert result.status_code==200 and result.json()['sessions_invalidated']
    assert other.get('/api/auth/me').status_code==401
    with st.db() as db:after=dict(db.execute('SELECT * FROM users WHERE id=?',(before['id'],)).fetchone())
    assert after['password']==before['password'] and after['factor']==before['factor'] and not after['enabled']
    assert after['generation']==before['generation']+1


def test_admin_cannot_disable_self_or_reuse_another_account_identity(environment):
    app,client,credentials,mail=environment;roman=enroll(environment)
    users=client.get('/api/users').json();own=next(x for x in users if x['username']=='Roman')
    data={key:own[key] for key in ['username','email','admin','language','enabled']}
    denied=post(client,'/api/users/'+str(own['id']),{**data,'enabled':False},roman['csrf'])
    assert denied.status_code==409 and client.get('/api/users').status_code==200
    duplicate=post(client,'/api/users/'+str(own['id']),{**data,'username':'Moritz'},roman['csrf'])
    assert duplicate.status_code==409
    assert post(client,'/api/users/'+str(own['id'])+'/recovery',{},roman['csrf']).status_code==409


def recovery_target(environment):
    app,client,credentials,mail=environment;roman=enroll(environment);other,_=second_account(environment)
    target=next(x for x in client.get('/api/users').json() if x['username']=='Moritz')
    result=post(client,'/api/users/'+str(target['id'])+'/recovery',{},roman['csrf'])
    assert result.status_code==200 and result.json()['factor_changed'] is False and 'token' not in result.text
    token=re.search(r'#recover=([A-Za-z0-9_-]+)',mail[-1]['body'])[1]
    return roman,other,target,token


def test_factor_recovery_needs_other_admin_email_link_and_existing_password(environment):
    app,client,credentials,mail=environment;roman,other,target,token=recovery_target(environment)
    denied=post(client,'/api/auth/recovery/complete',{'token':token,'password':'wrong-password'})
    assert denied.status_code==401 and other.get('/api/auth/me').json()['user']['factor']=='email'
    correct={'token':token,'password':'A-Strong-Test-Password-2026!'}
    result=post(client,'/api/auth/recovery/complete',correct)
    assert result.status_code==200 and result.json()['factor_setup_required']
    assert post(client,'/api/auth/recovery/complete',correct).status_code==401
    assert other.get('/api/auth/me').status_code==401
    with app.state.store.db() as db:
        user=dict(db.execute('SELECT * FROM users WHERE id=?',(target['id'],)).fetchone())
        assert user['factor'] is None and user['force_password']==1
        assert db.execute('SELECT COUNT(*) FROM recovery_codes WHERE user_id=?',(target['id'],)).fetchone()[0]==0
    login_result=post(other,'/api/auth/login',{'username':'Moritz','password':correct['password']})
    assert login_result.status_code==200
    assert other.get('/api/overview').status_code==403
    assert any(x['event']=='factor_recovery_completed' for x in client.get('/api/events').json())


@pytest.mark.parametrize('change',['expired','email','initiator_revoked'])
def test_recovery_invalidated_by_expiry_account_change_or_initiator_revocation(environment,change):
    app,client,credentials,mail=environment;roman,other,target,token=recovery_target(environment)
    with app.state.store.db() as db:
        if change=='expired':db.execute('UPDATE challenges SET expires=0 WHERE kind=?',('admin_recovery',))
        if change=='email':db.execute('UPDATE users SET email=? WHERE id=?',('changed@example.test',target['id']))
        if change=='initiator_revoked':db.execute("UPDATE users SET admin=0 WHERE username='Roman'")
    result=post(client,'/api/auth/recovery/complete',{'token':token,'password':'A-Strong-Test-Password-2026!'})
    assert result.status_code==401
    with app.state.store.db() as db:assert db.execute('SELECT factor FROM users WHERE id=?',(target['id'],)).fetchone()[0]=='email'

def jar(entries):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive:
        for name,content in entries.items():archive.writestr(name,content)
    return data.getvalue()

def test_jar_path_traversal_rejected():
    raw=jar({'../escape':'malicious','fabric.mod.json':'{"id":"safe_mod","version":"1.0"}'})
    with pytest.raises(ValueError,match='jar_unsafe_path'):mods.inspect_jar(raw)

def test_staging_is_not_installation(environment):
    app,client,creds,mail=environment
    raw=jar({'fabric.mod.json':'{"id":"safe_mod","version":"1.0","depends":{"minecraft":"1.20.1"}}'})
    result=mods.stage(app.state.store,app.state.store.state.parent,raw,'safe.jar')
    assert result['state']=='staged'
    assert not (app.state.store.state.parent/'server/mods/safe.jar').exists()
    with app.state.store.db() as db:row=dict(db.execute('SELECT * FROM mods').fetchone())
    report=mods.dependency_report([row],app.state.store.get('server'))
    assert any(x['issue']=='version_mismatch' for x in report['issues'])
    wrong_loader=mods.dependency_report([row],{**app.state.store.get('server'),'loader':'FORGE'})
    assert any(x['issue']=='loader_mismatch' for x in wrong_loader['issues'])
    assert report['runtime_compatibility']=='unverified'

def test_discord_endpoint_allowlist():
    for value in ['http://discord.com/api/webhooks/1/token','https://evil.example/api/webhooks/1/token',
                  'https://discord.com@evil.example/api/webhooks/1/token','https://discord.com/api/webhooks/1/token?redirect=x']:
        with pytest.raises(ValueError):notify.discord_url(value)

def test_consistent_sqlite_backup(environment,tmp_path):
    app,client,creds,mail=environment
    backup=tmp_path/'snapshot.sqlite3';app.state.store.sqlite_backup(backup)
    import sqlite3
    with sqlite3.connect(backup) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==2

def test_language_before_mfa_does_not_grant_privileges(environment):
    app,client,creds,mail=environment;csrf=login(environment,'Moritz')
    assert post(client,'/api/auth/language',{'language':'en'},csrf).status_code==200
    assert client.get('/api/auth/me').json()['user']['language']=='en'
    assert client.get('/api/overview').status_code==403

def test_validation_errors_do_not_echo_password(environment):
    app,client,creds,mail=environment;csrf=login(environment)
    supplied='bad-secret'
    result=post(client,'/api/auth/password',{'current':creds['Roman']['password'],'password':supplied},csrf)
    assert result.status_code==422
    assert supplied not in result.text and creds['Roman']['password'] not in result.text

def test_provider_key_is_encrypted_masked_and_not_in_diagnostics(environment):
    app,client,creds,mail=environment;result=enroll(environment)
    key='acceptance-private-provider-key'
    assert post(client,'/api/settings',{'section':'providers','value':{'curseforge_api_key':key}},result['csrf']).status_code==200
    settings=client.get('/api/settings').json()
    assert settings['providers']=={'curseforge_api_key_configured':True}
    assert key not in client.get('/api/diagnostics').text and key not in client.get('/api/events/export').text
    with app.state.store.db() as db:
        row=db.execute("SELECT * FROM settings WHERE name='providers'").fetchone()
        assert row['secret']==1 and key not in row['value']
    assert post(client,'/api/settings',{'section':'providers','value':{'curseforge_api_key':''}},result['csrf']).status_code==200
    assert app.state.store.get('providers')['curseforge_api_key']==key


def test_settings_game_publication_reflects_declared_release(environment):
    app,client,_,_=environment;enroll(environment)
    for published in [False,True]:
        current=app.state.store.get('release');current['public_game']=published;app.state.store.set('release',current)
        assert client.get('/api/settings').json()['infrastructure']['game_published'] is published

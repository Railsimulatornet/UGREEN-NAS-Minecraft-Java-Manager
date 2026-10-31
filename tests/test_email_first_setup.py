"""First sign-in without an authenticator; real local TLS SMTP and receipt proof."""
import base64
import datetime
import email.policy
import ipaddress
import json
import re
import socketserver
import ssl
import threading
import time
from email.parser import BytesParser

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from mcj import auth, notify
from test_security import environment, login, post


class Mailbox(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Smtp(socketserver.StreamRequestHandler):
    def handle(self):
        server = self.server
        secure = False
        if server.transport == 'tls':
            self.connection = server.context.wrap_socket(self.connection, server_side=True)
            self.rfile = self.connection.makefile('rb')
            self.wfile = self.connection.makefile('wb')
            secure = True

        def reply(value):
            self.wfile.write(value + b'\r\n')
            self.wfile.flush()

        reply(b'220 local-test-mailbox')
        authenticated = False
        recipient = None
        while True:
            line = self.rfile.readline(16384)
            if not line:
                return
            command = line.split(b' ', 1)[0].strip().upper()
            if command == b'EHLO':
                reply(b'250-local-test-mailbox')
                if not secure and server.offer_starttls:
                    reply(b'250-STARTTLS')
                reply(b'250 AUTH PLAIN')
            elif command == b'STARTTLS':
                reply(b'220 ready for TLS')
                self.connection = server.context.wrap_socket(self.connection, server_side=True)
                self.rfile = self.connection.makefile('rb')
                self.wfile = self.connection.makefile('wb')
                secure = True
            elif command == b'AUTH':
                assert secure, 'credentials must never cross an unencrypted connection'
                parts = line.strip().split(b' ')
                if len(parts) == 2:
                    reply(b'334 ')
                    raw = self.rfile.readline().strip()
                else:
                    raw = parts[-1]
                credentials = base64.b64decode(raw).split(b'\x00')
                authenticated = credentials[-1] == b'disposable-smtp-password'
                reply(b'235 signed in' if authenticated else b'535 incorrect credentials')
            elif command == b'MAIL':
                reply(b'250 sender accepted' if authenticated else b'530 sign in first')
            elif command == b'RCPT':
                recipient = line.decode().strip().split(':', 1)[1].strip('<> ')
                reply(b'250 recipient accepted')
            elif command == b'DATA':
                assert secure and authenticated
                reply(b'354 send message')
                data = []
                while True:
                    part = self.rfile.readline(16384)
                    if part == b'.\r\n':
                        break
                    if not part:
                        return
                    data.append(part[1:] if part.startswith(b'..') else part)
                message = BytesParser(policy=email.policy.default).parsebytes(b''.join(data))
                server.messages.append({'recipient': recipient, 'message': message, 'tls': secure})
                reply(b'250 delivered to local mailbox')
            elif command == b'QUIT':
                reply(b'221 bye')
                return
            elif command == b'RSET':
                reply(b'250 reset')
            else:
                reply(b'500 unsupported command')


@pytest.fixture
def tls_mailbox(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
                           x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_file = tmp_path / 'local-test.crt'
    key_file = tmp_path / 'local-test.key'
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    original = ssl.create_default_context
    # Trust this disposable test certificate, retaining hostname verification and TLS.
    monkeypatch.setattr(notify.ssl, 'create_default_context', lambda: original(cafile=str(cert_file)))
    servers = []

    def start(transport='starttls', offer_starttls=True):
        server = Mailbox(('127.0.0.1', 0), Smtp)
        server.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.context.load_cert_chain(str(cert_file), str(key_file))
        server.messages = []
        server.transport = transport
        server.offer_starttls = offer_starttls
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server

    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def pending(environment, language='de'):
    app, client, creds, _ = environment
    csrf = login(environment)
    result = post(client, '/api/auth/password', {'current': creds['Roman']['password'],
                  'password': 'Safe-First-Email-Password-2026!'}, csrf)
    assert result.status_code == 200
    csrf = result.json()['csrf']
    assert post(client, '/api/auth/language', {'language': language}, csrf).status_code == 200
    return csrf


def settings(server, transport='starttls'):
    return {'host': 'localhost', 'port': server.server_address[1], 'security': transport,
            'username': 'sender@example.test', 'sender': 'sender@example.test',
            'password': 'disposable-smtp-password'}


def received_code(server):
    return re.search(r'\b[0-9]{6}\b', server.messages[-1]['message'].get_content())[0]


def begin(environment, monkeypatch, cfg, csrf):
    # Replace only the legacy capture fixture; exercise the actual mail transport.
    monkeypatch.setattr(auth, 'send_email', notify.send_email)
    return post(environment[1], '/api/auth/setup/email/smtp', cfg, csrf)


@pytest.mark.parametrize('transport', ['starttls', 'tls'])
@pytest.mark.parametrize('language', ['de', 'en'])
def test_fresh_empty_smtp_receipt_relogin_and_single_use_recovery(environment, tls_mailbox, monkeypatch, transport, language):
    app, client, _, _ = environment
    st = app.state.store
    assert st.get('smtp')['host'] == ''
    csrf = pending(environment, language)
    assert client.get('/api/auth/setup/email/status').json() == {'configured': False, 'can_configure': True}
    server = tls_mailbox(transport)
    response = begin(environment, monkeypatch, settings(server, transport), csrf)
    assert response.status_code == 200
    token = response.json()['challenge']
    assert set(response.json()) == {'challenge'}
    assert len(server.messages) == 1 and server.messages[0]['tls']
    assert server.messages[0]['recipient'] == 'roman@example.invalid'
    assert ('Dein Sicherheitscode' if language == 'de' else 'Your security code') in server.messages[0]['message'].get_content()
    assert st.get('smtp')['host'] == ''  # SMTP acceptance alone never enables email.
    assert client.get('/api/settings').status_code == 403
    code = received_code(server)
    raw = st.path.read_bytes()
    assert b'disposable-smtp-password' not in raw
    answer = post(client, '/api/auth/setup/confirm', {'method': 'email', 'challenge': token, 'code': code}, csrf)
    assert answer.status_code == 200
    result = answer.json()
    assert len(result['backup_codes']) == 10
    assert st.get('smtp') == settings(server, transport)
    me = client.get('/api/auth/me').json()
    assert me['mfa_verified'] and me['user']['factor'] == 'email'
    with st.db() as db:
        assert db.execute('SELECT totp FROM users WHERE id=1').fetchone()[0] is None
        assert db.execute("SELECT COUNT(*) FROM challenges WHERE kind='enroll_email'").fetchone()[0] == 0
        events = ' '.join(row['data'] for row in db.execute('SELECT data FROM events'))
    assert code not in events and 'disposable-smtp-password' not in events
    # A permitted normal profile change does not ask for another security code.
    assert post(client, '/api/auth/language', {'language': language}, result['csrf']).status_code == 200
    assert len(server.messages) == 1
    assert post(client, '/api/auth/logout', csrf=result['csrf']).status_code == 200
    logged = post(client, '/api/auth/login', {'username': 'Roman', 'password': 'Safe-First-Email-Password-2026!'}).json()
    assert logged['mfa_required'] and len(server.messages) == 2
    assert client.get('/api/settings').status_code == 403
    signed = post(client, '/api/auth/verify', {'challenge': logged['challenge'], 'code': received_code(server)}, logged['csrf'])
    assert signed.status_code == 200
    assert post(client, '/api/auth/logout', csrf=signed.json()['csrf']).status_code == 200
    logged = post(client, '/api/auth/login', {'username': 'Roman', 'password': 'Safe-First-Email-Password-2026!'}).json()
    recovered = post(client, '/api/auth/verify', {'recovery': True, 'code': result['backup_codes'][0]}, logged['csrf'])
    assert recovered.status_code == 200
    assert post(client, '/api/auth/logout', csrf=recovered.json()['csrf']).status_code == 200
    logged = post(client, '/api/auth/login', {'username': 'Roman', 'password': 'Safe-First-Email-Password-2026!'}).json()
    assert post(client, '/api/auth/verify', {'recovery': True, 'code': result['backup_codes'][0]}, logged['csrf']).status_code == 401


@pytest.mark.parametrize('failure', ['wrong', 'expired', 'attempts', 'other_session', 'email_changed', 'smtp_changed'])
def test_invalid_receipt_never_installs_mail_or_factor(environment, tls_mailbox, monkeypatch, failure):
    app, client, _, _ = environment
    csrf = pending(environment)
    server = tls_mailbox()
    setup = begin(environment, monkeypatch, settings(server), csrf).json()
    code = received_code(server)
    st = app.state.store
    if failure == 'wrong':code = 'not-the-code'
    elif failure == 'expired':
        with st.db() as db:db.execute('UPDATE challenges SET expires=?', (time.time()-1,))
    elif failure == 'attempts':
        for _ in range(5):
            assert post(client, '/api/auth/setup/confirm', {'method':'email','challenge':setup['challenge'],'code':'bad'}, csrf).status_code == 401
    elif failure == 'other_session':
        other = TestClient(app, base_url='https://testserver')
        csrf = post(other, '/api/auth/login', {'username':'Roman','password':'Safe-First-Email-Password-2026!'}).json()['csrf']
        client = other
    elif failure == 'email_changed':
        with st.db() as db:db.execute("UPDATE users SET email='changed@example.test' WHERE id=1")
    elif failure == 'smtp_changed':
        cfg=st.get('smtp');cfg['port']=465;st.set('smtp',cfg,True)
    response = post(client, '/api/auth/setup/confirm', {'method':'email','challenge':setup['challenge'],'code':code}, csrf)
    assert response.status_code == 401
    assert st.get('smtp')['host'] == ''
    assert client.get('/api/auth/me').json()['user']['factor'] is None
    assert client.get('/api/settings').status_code == 403


@pytest.mark.parametrize('failure,expected', [('credentials','smtp_authentication_failed'),('no_starttls','smtp_secure_connection_failed'),('unreachable','smtp_connection_failed')])
def test_delivery_error_is_clear_secret_free_and_allows_totp(environment, tls_mailbox, monkeypatch, failure, expected):
    app, client, _, _ = environment
    csrf = pending(environment)
    server = tls_mailbox(offer_starttls=failure!='no_starttls')
    cfg = settings(server)
    if failure=='credentials':cfg['password']='intentionally-wrong-disposable-secret'
    if failure=='unreachable':cfg['host']='no-mail-server.invalid'
    response = begin(environment, monkeypatch, cfg, csrf)
    assert response.status_code == 502 and response.json()['detail']==expected
    assert cfg['password'] not in response.text
    st = app.state.store
    assert not st.get('smtp')['host']
    with st.db() as db:
        assert not db.execute("SELECT 1 FROM challenges WHERE kind='enroll_email'").fetchone()
        assert cfg['password'] not in str([tuple(r) for r in db.execute('SELECT * FROM events')])
    assert post(client, '/api/auth/setup/totp', csrf=csrf).status_code == 200


def test_first_smtp_requires_password_change_admin_origin_csrf_and_keeps_other_accounts(environment, tls_mailbox, monkeypatch):
    app, client, _, _ = environment
    server = tls_mailbox();cfg=settings(server)
    monkeypatch.setattr(auth,'send_email',notify.send_email)
    assert post(client,'/api/auth/setup/email/smtp',cfg).status_code==403
    csrf=login(environment)
    assert post(client,'/api/auth/setup/email/smtp',cfg,csrf).status_code==403
    csrf=pending(environment)
    assert post(client,'/api/auth/setup/email/smtp',cfg).status_code==403
    assert post(client,'/api/auth/setup/email/smtp',cfg,csrf,origin='https://foreign.invalid').status_code==403
    with app.state.store.db() as db:
        db.execute('UPDATE users SET admin=0 WHERE id=1')
        other_before=tuple(db.execute('SELECT * FROM users WHERE id=2').fetchone())
    assert post(client,'/api/auth/setup/email/smtp',cfg,csrf).status_code==403
    assert client.get('/api/auth/setup/email/status').json()=={'configured':False,'can_configure':False}
    with app.state.store.db() as db:
        db.execute('UPDATE users SET admin=1 WHERE id=1')
    setup=post(client,'/api/auth/setup/email/smtp',cfg,csrf).json()
    result=post(client,'/api/auth/setup/confirm',{'method':'email','challenge':setup['challenge'],'code':received_code(server)},csrf)
    assert result.status_code==200
    with app.state.store.db() as db:assert tuple(db.execute('SELECT * FROM users WHERE id=2').fetchone())==other_before
    assert post(client,'/api/auth/setup/email/smtp',cfg,result.json()['csrf']).status_code==409


def test_invalid_config_is_redacted_and_uses_encryption_only(environment, tls_mailbox):
    _,client,_,_=environment;csrf=pending(environment)
    cfg=settings(tls_mailbox())
    for change in [{'security':'none'},{'password':'x'*1001},{'port':True},{'extra_secret':'never-reflect-this-secret'},{'username':'a\r\nInjected: header'}]:
        response=post(client,'/api/auth/setup/email/smtp',{**cfg,**change},csrf)
        assert response.status_code==422 and response.json()=={'detail':'invalid_request'}


def test_only_one_competing_admin_can_commit_initial_mail_settings(environment, tls_mailbox, monkeypatch):
    app,client,creds,_=environment;csrf=pending(environment)
    server=tls_mailbox();cfg=settings(server)
    first=begin(environment,monkeypatch,cfg,csrf).json();code=received_code(server)
    second=TestClient(app,base_url='https://testserver')
    token=post(second,'/api/auth/login',{'username':'Moritz','password':creds['Moritz']['password']}).json()['csrf']
    token=post(second,'/api/auth/password',{'current':creds['Moritz']['password'],'password':'Safe-Other-Email-Password-2026!'},token).json()['csrf']
    another=post(second,'/api/auth/setup/email/smtp',cfg,token).json();other_code=received_code(server)
    assert post(client,'/api/auth/setup/confirm',{'method':'email','challenge':first['challenge'],'code':code},csrf).status_code==200
    assert post(second,'/api/auth/setup/confirm',{'method':'email','challenge':another['challenge'],'code':other_code},token).status_code==401
    assert app.state.store.get('smtp')==cfg
    assert second.get('/api/auth/me').json()['user']['factor'] is None


def test_rejected_tls_certificate_never_sends_credentials_or_enables_email(environment,tls_mailbox,monkeypatch):
    _,client,_,_=environment;csrf=pending(environment);server=tls_mailbox()
    def system_trust_only():
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.load_default_certs();return context
    monkeypatch.setattr(notify.ssl,'create_default_context',system_trust_only)
    answer=begin(environment,monkeypatch,settings(server),csrf)
    assert answer.status_code==502 and answer.json()['detail']=='smtp_secure_connection_failed'
    assert not server.messages
    assert client.get('/api/auth/me').json()['user']['factor'] is None


def test_later_mail_outage_keeps_existing_factor_and_offers_recovery(environment,tls_mailbox,monkeypatch):
    app,client,_,_=environment;csrf=pending(environment);server=tls_mailbox()
    start=begin(environment,monkeypatch,settings(server),csrf).json()
    result=post(client,'/api/auth/setup/confirm',{'method':'email','challenge':start['challenge'],'code':received_code(server)},csrf).json()
    post(client,'/api/auth/logout',csrf=result['csrf'])
    def unavailable(*args,**kwargs):raise notify.MailDeliveryError('smtp_authentication_failed')
    monkeypatch.setattr(auth,'send_email',unavailable)
    reply=post(client,'/api/auth/login',{'username':'Roman','password':'Safe-First-Email-Password-2026!'})
    assert reply.status_code==200
    login=reply.json();assert login['email_delivery_error']=='email_login_delivery_failed' and 'challenge' not in login
    assert client.get('/api/auth/me').json()['user']['factor']=='email'
    assert client.get('/api/settings').status_code==403
    resend=post(client,'/api/auth/email-challenge',csrf=login['csrf'])
    assert resend.status_code==502 and resend.json()['detail']=='email_login_delivery_failed'
    verify=post(client,'/api/auth/verify',{'recovery':True,'code':result['backup_codes'][0]},login['csrf'])
    assert verify.status_code==200 and client.get('/api/settings').status_code==200


def test_actual_fresh_initializer_supports_email_without_totp_or_previous_smtp(tmp_path,monkeypatch,tls_mailbox):
    from pathlib import Path
    from cryptography.fernet import Fernet
    from mcj.web import create_app
    from test_installation import module
    root=tmp_path/'fresh'
    for part in ('manager/state','manager/secrets','mcj_controller/control/runtime','mcj_controller/control/roles','mcj_minecraft/data/mods'):
        (root/part).mkdir(parents=True,exist_ok=True)
    (root/'manager/secrets/encryption').write_bytes(Fernet.generate_key())
    (root/'manager/secrets/rcon').write_text('disposable-local-rcon-secret')
    project=Path(__file__).parents[1];guard=json.loads((project/'artifacts/guard.json').read_text())
    (root/'mcj_controller/control/runtime/guard.json').write_text(json.dumps(guard))
    (root/'mcj_minecraft/data/mods'/guard['filename']).write_bytes((project/'artifacts'/guard['filename']).read_bytes())
    initializer=module('initialize_installation')
    cfg={'username':'Owner','email':'owner@example.test','origin':'https://testserver','initial_password_chosen':True}
    password='Safe-Fresh-Install-Password-2026!'
    initializer.initialize(root,cfg,password)  # Account initialization only; no Docker or game start.
    monkeypatch.setenv('MCJ_LAYOUT','services-v1')
    app=create_app(root=root,keyfile=root/'manager/secrets/encryption',origin=cfg['origin'],start_worker=False)
    client=TestClient(app,base_url=cfg['origin'],client=('127.0.0.1',50000))
    response=post(client,'/api/auth/login',{'username':'Owner','password':password})
    assert response.status_code==200
    login=response.json()
    assert not login['user']['force_password'] and login['user']['factor'] is None
    assert app.state.store.get('smtp')['host']==''
    server=tls_mailbox();monkeypatch.setattr(auth,'send_email',notify.send_email)
    setup=post(client,'/api/auth/setup/email/smtp',settings(server),login['csrf'])
    assert setup.status_code==200 and server.messages[-1]['recipient']=='owner@example.test'
    confirmed=post(client,'/api/auth/setup/confirm',{'method':'email','challenge':setup.json()['challenge'],'code':received_code(server)},login['csrf'])
    assert confirmed.status_code==200
    assert client.get('/api/auth/me').json()['mfa_verified']
    assert app.state.store.get('smtp')['host']=='localhost'
    with app.state.store.db() as db:
        assert db.execute('SELECT factor,totp FROM users').fetchone()[:]==('email',None)

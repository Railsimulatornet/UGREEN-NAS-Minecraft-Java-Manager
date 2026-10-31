from datetime import datetime,timedelta,timezone
import hashlib,json,socket,ssl,threading,time
import pytest
from cryptography import x509
from mcj import local_tls
from test_security import environment,enroll,login,post


@pytest.fixture
def authority(tmp_path):
    base=tmp_path/'tls';local_tls.create(base,'192.168.1.50');return base


def test_local_authority_has_only_a_constrained_persistent_signer(authority):
    base=authority;root=x509.load_pem_x509_certificate((base/'authority.crt').read_bytes());issuer=x509.load_pem_x509_certificate((base/'issuer.crt').read_bytes())
    issuer.verify_directly_issued_by(root)
    constraints=issuer.extensions.get_extension_for_class(x509.NameConstraints)
    assert constraints.critical and {str(x.value) for x in constraints.value.permitted_subtrees}=={'192.168.1.50/32','127.0.0.1/32','localhost'}
    assert issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length==0
    assert not (base/'authority.key').exists()
    value=local_tls.status(base)
    assert 'PRIVATE KEY' not in json.dumps(value) and value['managed']
    with pytest.raises(ValueError,match='already_configured'):local_tls.create(base,'192.168.1.50')


def test_actual_tls_handshake_and_hot_renewal_keep_the_same_trust(authority):
    base=authority;cert,key=local_tls.files(base);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    client=ssl.create_default_context(cafile=str(base/'authority.crt'))
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(2);listener.settimeout(5);errors=[]
    def serve():
        try:
            for _ in range(2):
                raw,_=listener.accept()
                with context.wrap_socket(raw,server_side=True) as connection:connection.sendall(b'OK')
        except Exception as exc:errors.append(type(exc).__name__)
        finally:listener.close()
    worker=threading.Thread(target=serve,daemon=True);worker.start()
    def connect():
        with client.wrap_socket(socket.socket(),server_hostname='127.0.0.1') as connection:
            connection.settimeout(5);connection.connect(listener.getsockname());fingerprint=hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest();assert connection.recv(2)==b'OK';return fingerprint
    first=connect();old=local_tls.status(base)
    new=local_tls.renew(base,lambda c,k:context.load_cert_chain(c,k))
    assert new['authority_fingerprint']==old['authority_fingerprint'] and new['serial']!=old['serial']
    assert connect()!=first;worker.join(5);assert not worker.is_alive() and not errors


def test_renewal_failure_preserves_the_existing_identity(authority):
    old=local_tls.identity(authority);calls=[]
    def reload(cert,key):
        calls.append((cert,key))
        if len(calls)==1:raise OSError('Fixture reload failure')
    with pytest.raises(OSError):local_tls.renew(authority,reload)
    assert local_tls.identity(authority)==old and len(calls)==2
    with pytest.raises(ValueError,match='authority_renewal_required'):
        local_tls.renew(authority,now=datetime.now(timezone.utc)+timedelta(days=1824))


def test_certificate_api_requires_admin_mfa_csrf_and_confirmation(environment,authority,monkeypatch):
    app,client,_,_=environment;monkeypatch.setenv('MCJ_TLS_MODE','selfsigned');monkeypatch.setenv('MCJ_TLS_DIR',str(authority));calls=[];app.state.tls_reload=lambda c,k:calls.append((c,k))
    assert client.get('/api/infrastructure/tls').status_code==401
    login(environment);assert client.get('/api/infrastructure/tls').status_code==403
    csrf=enroll(environment)['csrf']
    assert client.get('/api/infrastructure/tls').json()['managed']
    cert=client.get('/api/infrastructure/tls/authority');assert cert.status_code==200 and 'BEGIN CERTIFICATE' in cert.text and 'PRIVATE KEY' not in cert.text
    assert post(client,'/api/infrastructure/tls/renew',{'confirmed':True}).status_code==403
    assert post(client,'/api/infrastructure/tls/renew',{},csrf).status_code==409
    changed=post(client,'/api/infrastructure/tls/renew',{'confirmed':True},csrf)
    assert changed.status_code==200 and changed.json()['minecraft_restart_required'] is False and calls
    with app.state.store.db() as db:db.execute('UPDATE sessions SET mfa=?',(time.time()-360,))
    assert post(client,'/api/infrastructure/tls/renew',{'confirmed':True},csrf).status_code==200
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/infrastructure/tls/authority').status_code==403


@pytest.mark.parametrize('address',['0.0.0.0','8.8.8.8','fe80::1'])
def test_initial_local_certificate_refuses_public_or_unspecified_addresses(tmp_path,address):
    with pytest.raises(ValueError):local_tls.create(tmp_path/'tls',address)

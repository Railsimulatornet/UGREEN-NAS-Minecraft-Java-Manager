"""Installation-local HTTPS. A constrained issuer allows renewal without changing trust."""
from datetime import datetime,timedelta,timezone
import ipaddress,json,os,re,secrets,stat
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID

UTC=timezone.utc


def _write(path,raw,mode):
    if path.is_symlink():raise ValueError('tls_unsafe_path')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),mode)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)


def _key():return rsa.generate_private_key(public_exponent=65537,key_size=3072)
def _pem(key):return key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
def _name(value):return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,value)])
def _cert_pem(cert):return cert.public_bytes(serialization.Encoding.PEM)
def _fingerprint(cert):return ':'.join(f'{x:02X}' for x in cert.fingerprint(hashes.SHA256()))


def _builder(subject,issuer,key,days,now):
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=days))
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False))


def _safe_file(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('tls_unsafe_path')
    return path.read_bytes()


def identity(base):
    base=Path(base)
    if base.is_symlink():raise ValueError('tls_unsafe_path')
    value=json.loads(_safe_file(base/'identity.json'))
    if not re.fullmatch('[a-f0-9]{32}',value.get('active','')):raise ValueError('tls_unsafe_path')
    return value


def files(base):
    base=Path(base);value=identity(base);generation=base/'generations'/value['active']
    if (base/'generations').is_symlink() or generation.is_symlink():raise ValueError('tls_unsafe_path')
    _safe_file(generation/'server.key');_safe_file(generation/'server.crt')
    return generation/'server.crt',generation/'server.key'


def _leaf(base,value,issuer,issuer_key,now):
    expiry=min(now+timedelta(days=397),issuer.not_valid_after_utc-timedelta(days=1))
    if expiry<=now+timedelta(days=7):raise ValueError('tls_authority_renewal_required')
    key=_key();subject=_name('MCJ Manager '+value['address'])
    cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(issuer.subject).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(expiry)
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(value['address'])),x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.DNSName('localhost')]),critical=False)
          .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
          .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=True,data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,encipher_only=False,decipher_only=False),critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),critical=False)
          .sign(issuer_key,hashes.SHA256()))
    identifier=secrets.token_hex(16);folder=base/'generations'/identifier;folder.mkdir(mode=0o700)
    _write(folder/'server.key',_pem(key),0o400);_write(folder/'server.crt',_cert_pem(cert)+_cert_pem(issuer),0o644)
    return identifier,cert


def create(base,address,now=None):
    base=Path(base);now=now or datetime.now(UTC);address=ipaddress.ip_address(address)
    if address.version!=4 or not any(address in ipaddress.ip_network(cidr) for cidr in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']):raise ValueError('tls_private_address_required')
    if base.is_symlink() or (base/'identity.json').exists():raise ValueError('tls_already_configured')
    base.mkdir(parents=True,exist_ok=True,mode=0o700);base.chmod(0o700);(base/'generations').mkdir(mode=0o700)
    root_key=_key();root_name=_name('MCJ local trust '+secrets.token_hex(8))
    root=(_builder(root_name,root_name,root_key,3650,now)
          .add_extension(x509.BasicConstraints(ca=True,path_length=1),critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False,content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=False,decipher_only=False),critical=True)
          .sign(root_key,hashes.SHA256()))
    issuer_key=_key();issuer=(_builder(_name('MCJ issuer '+str(address)),root.subject,issuer_key,1825,now)
          .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False,content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=False,decipher_only=False),critical=True)
          .add_extension(x509.NameConstraints(permitted_subtrees=[x509.IPAddress(ipaddress.ip_network(str(address)+'/32')),x509.IPAddress(ipaddress.ip_network('127.0.0.1/32')),x509.DNSName('localhost')],excluded_subtrees=None),critical=True)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),critical=False)
          .sign(root_key,hashes.SHA256()))
    # The unconstrained root signing key is never persisted. Only the constrained issuer remains.
    _write(base/'authority.crt',_cert_pem(root),0o644);_write(base/'issuer.crt',_cert_pem(issuer),0o644);_write(base/'issuer.key',_pem(issuer_key),0o400)
    value={'schema':1,'address':str(address),'authority_fingerprint':_fingerprint(root)}
    identifier,_=_leaf(base,value,issuer,issuer_key,now);value['active']=identifier
    _write(base/'identity.json',(json.dumps(value)+'\n').encode(),0o640)
    return status(base)


def status(base):
    base=Path(base);value=identity(base);cert_path,_=files(base)
    cert=x509.load_pem_x509_certificate(_safe_file(cert_path));authority=x509.load_pem_x509_certificate(_safe_file(base/'authority.crt'))
    if value['authority_fingerprint']!=_fingerprint(authority):raise ValueError('tls_authority_mismatch')
    return {'mode':'selfsigned','managed':True,'address':value['address'],'expires':cert.not_valid_after_utc.timestamp(),
            'fingerprint':_fingerprint(cert),'authority_fingerprint':_fingerprint(authority),'authority_expires':authority.not_valid_after_utc.timestamp(),'serial':str(cert.serial_number)}


def renew(base,reload=None,now=None):
    base=Path(base);now=now or datetime.now(UTC);value=identity(base);old=files(base)
    authority=x509.load_pem_x509_certificate(_safe_file(base/'authority.crt'));issuer=x509.load_pem_x509_certificate(_safe_file(base/'issuer.crt'));issuer.verify_directly_issued_by(authority)
    if _fingerprint(authority)!=value['authority_fingerprint']:raise ValueError('tls_authority_mismatch')
    issuer_key=serialization.load_pem_private_key(_safe_file(base/'issuer.key'),password=None)
    if issuer_key.public_key().public_numbers()!=issuer.public_key().public_numbers():raise ValueError('tls_issuer_mismatch')
    identifier,_=_leaf(base,value,issuer,issuer_key,now);folder=base/'generations'/identifier
    new={**value,'active':identifier};temporary=base/('identity-'+secrets.token_hex(8)+'.tmp')
    try:
        if reload:reload(folder/'server.crt',folder/'server.key')
        _write(temporary,(json.dumps(new)+'\n').encode(),0o640);os.replace(temporary,base/'identity.json')
    except Exception:
        if reload:reload(*old)
        if temporary.exists():temporary.unlink()
        raise
    return status(base)

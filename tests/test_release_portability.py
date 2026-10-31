import json
import ast,re
from pathlib import Path
from cryptography.fernet import Fernet
from mcj.store import Store

def test_acceptance_sources_do_not_embed_personal_email_addresses():
    root=Path(__file__).parent
    for path in root.glob('acceptance_*.py'):
        for item in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(item,ast.Constant) and isinstance(item.value,str):
                for domain in re.findall(r'[A-Za-z0-9_.+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})',item.value):
                    assert domain.lower().endswith(('.invalid','.test','.example')) or domain.lower() in {'example.com','example.net','example.org'},(path.name,item.lineno,domain)


def test_empty_fallback_contains_only_a_neutral_owner_and_no_private_smtp(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());bootstrap=tmp_path/'bootstrap'
    st=Store(tmp_path/'state',key,bootstrap)
    with st.db() as db:users=[dict(x) for x in db.execute('SELECT username,email,force_password,factor,password FROM users')]
    assert len(users)==1 and users[0]['username']=='Owner' and users[0]['email']=='owner@example.invalid'
    assert users[0]['force_password'] and not users[0]['factor'] and users[0]['password'].startswith('$argon2id$')
    smtp=st.get('smtp');assert not any(smtp[x] for x in ['host','username','sender','password']) and smtp['security']=='starttls'
    generated=json.loads(st.cipher.decrypt(bootstrap.read_bytes()));assert len(generated['Owner']['password'])>=24


def test_existing_accounts_and_encrypted_mail_settings_survive_neutral_defaults(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    st=Store(tmp_path/'state',key,initial_accounts=[{'username':'ExistingAdmin','email':'admin@example.invalid'}])
    mail={'host':'smtp.example.invalid','port':587,'security':'starttls','username':'admin@example.invalid','sender':'admin@example.invalid','password':'owned-fixture-secret'}
    st.set('smtp',mail,True)
    with st.db() as db:
        before_users=[tuple(x) for x in db.execute('SELECT * FROM users')]
        before_mail=tuple(db.execute("SELECT value,secret FROM settings WHERE name='smtp'").fetchone())
    reopened=Store(st.state,key)
    with reopened.db() as db:
        assert before_users==[tuple(x) for x in db.execute('SELECT * FROM users')]
        assert before_mail==tuple(db.execute("SELECT value,secret FROM settings WHERE name='smtp'").fetchone())
    assert reopened.get('smtp')==mail


def test_bundled_font_keeps_its_original_license():
    root=Path(__file__).parents[1]
    text=(root/'mcj/static/assets/licenses/PixelifySans-OFL.txt').read_text(encoding='utf-8')
    assert 'SIL OPEN FONT LICENSE Version 1.1' in text and 'Pixelify Sans Project Authors' in text

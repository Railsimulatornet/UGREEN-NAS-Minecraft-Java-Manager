import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

from cryptography.fernet import Fernet
import pytest
import pyotp
from fastapi.testclient import TestClient

from mcj.store import Store, HASHER
from mcj.web import create_app
from mcj import properties

PROJECT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, PROJECT / 'tools' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


installer = module('install')
initializer = module('initialize_installation')
CONFIG = {'root': '/volume1/docker/minecraftjava', 'backup_root': '/volume1/Backups/MinecraftJava',
          'origin': 'https://minecraft.example.test', 'username': 'Owner',
          'email': 'owner@example.test', 'accept_eula': True}
PASSWORD = 'Fixture-Initial-Password-2026!'


@pytest.mark.parametrize('changes', [
    {'root': '/etc/minecraft'}, {'root': '/volume1/docker/../other'},
    {'root': '/volume1/docker/minecraft${HOME}'}, {'root': '/volume1/docker/a\nb'},
    {'backup_root': '/volume1/docker/minecraftjava/backups'},
    {'root': '/volume1/docker/minecraftjava/'}, {'origin': 'http://minecraft.example.test'},
    {'origin': 'https://user:pass@minecraft.example.test'},
    {'origin': 'https://minecraft.example.test/path'},
    {'origin': 'https://minecraft.example.test?token=x'},
    {'origin': 'https://minecraft.example.test#x'},
    {'origin': 'https://minecraft.example.test:99999'},
    {'accept_eula': False}, {'username': '../owner'}, {'email': 'owner\n@example.test'},
    {'password': PASSWORD},
])
def test_invalid_nonsecret_setup_refused(changes):
    with pytest.raises((ValueError, TypeError)):
        installer.validate(dict(CONFIG, **changes))


def test_valid_setup_and_portable_compose():
    config = installer.validate(dict(CONFIG, root='/volume4/docker/minecraft_anderes_nas', backup_root='/volume5/Backups/Spielserver', origin=CONFIG['origin'] + '/'))
    compose = installer.compose_text(config, 777)
    assert 'APP_ORIGIN: "https://minecraft.example.test"' in compose
    assert "'Host':'minecraft.example.test'" in compose
    assert 'group_add: ["777"]' in compose
    assert '/volume1/docker/minecraftjava' not in compose
    assert '/volume3/NASAdmin' not in compose
    assert config['root'] + '/mcj_minecraft/data:/data' in compose
    assert config['backup_root'] + ':/backups:ro' in compose
    assert config['backup_root'] + ':/backups' in compose
    assert '127.0.0.1:8090:8090/tcp' in compose
    assert '127.0.0.1:25565:25565/tcp' in compose
    assert compose.count('restart: unless-stopped') == 3
    assert compose.count('/var/run/docker.sock:/var/run/docker.sock') == 1

@pytest.mark.parametrize('backup_root',['/volume5/Backups/Spielserver','/volume1/docker/minecraftjava-archiv'])
def test_inserted_backup_path_is_not_rewritten_as_project_prefix(backup_root):
    config=dict(CONFIG,root='/volume4/docker/anderer_server',backup_root=backup_root)
    compose=installer.compose_text(config,777)
    assert backup_root+':/backups:ro' in compose
    assert config['root']+'-backups' not in compose

def test_explicit_private_nas_binding_is_consistent_with_controller():
    config=installer.validate(dict(CONFIG,game_bind_address='192.168.1.10'))
    compose=installer.compose_text(config,777)
    assert '192.168.1.10:25565:25565/tcp' in compose and 'GAME_BIND_ADDRESS: "192.168.1.10"' in compose
    for value in ['0.0.0.0','8.8.8.8','169.254.1.1','::1']:
        with pytest.raises(ValueError,match='setup_game_binding_invalid'):installer.validate(dict(CONFIG,game_bind_address=value))


@pytest.mark.parametrize('labels,name', [
    ({'com.docker.compose.project': installer.PROJECT, 'com.docker.compose.service': 'minecraft'}, '/different'),
    ({'com.docker.compose.project': 'other_actual_project', 'com.docker.compose.service': 'manager'}, '/mcj_manager'),
])
def test_existing_project_identity_refused_before_file_changes(tmp_path, monkeypatch, labels, name):
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, 'fixture-id\n' if args[0] == 'ps' else
                                           json.dumps([{'Name': name, 'Config': {'Labels': labels}}]))
    monkeypatch.setattr(installer, 'docker', run)
    config = dict(CONFIG, root=str(tmp_path / 'new'), backup_root=str(tmp_path / 'backups'))
    with pytest.raises(RuntimeError, match='existing_project_refused') as error:
        installer.preflight(config)
    assert labels['com.docker.compose.project'] in str(error.value)
    assert labels['com.docker.compose.service'] in str(error.value)
    assert not list(tmp_path.iterdir())
    assert [item[0] for item in calls] == ['ps', 'inspect']


def test_existing_path_refused_without_merging(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    existing = root / 'world.dat'
    existing.write_bytes(b'preserve-existing-world')
    before = hashlib.sha256(existing.read_bytes()).hexdigest()
    monkeypatch.setattr(installer, 'docker', lambda *a, **k: subprocess.CompletedProcess(a, 0, ''))
    with pytest.raises(RuntimeError, match='existing_installation_path_refused'):
        installer.preflight(dict(CONFIG, root=str(root), backup_root=str(tmp_path / 'backups')))
    assert hashlib.sha256(existing.read_bytes()).hexdigest() == before
    assert len(list(root.iterdir())) == 1


def test_custom_initial_accounts_and_existing_database_preserved(tmp_path):
    key = tmp_path / 'key'
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    bootstrap = tmp_path / 'bootstrap'
    st = Store(tmp_path / 'state', key, bootstrap, initial_accounts=[
        {'username': 'Owner', 'email': 'owner@example.test', 'password': PASSWORD}])
    with st.db() as db:
        users = [dict(row) for row in db.execute('SELECT * FROM users')]
    assert [(x['username'], x['email'], x['admin'], x['force_password']) for x in users] == [
        ('Owner', 'owner@example.test', 1, 1)]
    assert HASHER.verify(users[0]['password'], PASSWORD)
    assert PASSWORD.encode() not in bootstrap.read_bytes()
    st.set('smtp', {'password': 'fixture-saved-secret'}, True)
    reopened = Store(st.state, key, bootstrap, initial_accounts=[{'invalid': 'ignored for existing db'}])
    with reopened.db() as db:
        assert db.execute('SELECT password FROM users').fetchone()[0] == users[0]['password']
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
    assert reopened.get('smtp')['password'] == 'fixture-saved-secret'


@pytest.mark.parametrize('accounts', [[], [{'username': 'a', 'email': 'a@b.test'}],
    [{'username': 'Good', 'email': 'a@b.test', 'password': 'short'}],
    [{'username': 'Good', 'email': 'a@b.test'}, {'username': 'good', 'email': 'c@d.test'}],
    [{'username': 'Good', 'email': 'a@b.test'}, {'username': 'Other', 'email': 'A@B.TEST'}],
    [{'username': 'Good', 'email': 'invalid'}]])
def test_invalid_seed_is_atomic(tmp_path, accounts):
    key = tmp_path / 'key'
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    with pytest.raises(ValueError, match='initial_accounts_invalid'):
        Store(tmp_path / 'state', key, initial_accounts=accounts)
    import sqlite3
    with sqlite3.connect(tmp_path / 'state/manager.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


def test_prepared_tree_initialization_and_first_personal_login(tmp_path, monkeypatch):
    config = dict(CONFIG, root=str(tmp_path / 'project'), backup_root=str(tmp_path / 'backups'))
    guard = json.loads((PROJECT / 'artifacts/guard.json').read_text())
    raw = (PROJECT / 'artifacts' / guard['filename']).read_bytes()
    monkeypatch.setattr(installer.os, 'chown', lambda *args: None, raising=False)
    previous = os.umask(0o077)
    try:
        compose = installer.prepare(config, guard, raw, 777)
    finally:
        os.umask(previous)
    root = compose.parent
    assert (root/'manager/source/start-game.sh').read_bytes()==(PROJECT/'start-game.sh').read_bytes()
    assert (root/'manager/source/deploy/ugos-aktualisierung.yaml').read_bytes()==(PROJECT/'deploy/ugos-aktualisierung.yaml').read_bytes()
    mode=(root/'manager/source/start-game.sh').stat().st_mode&0o777
    assert mode==0o550 if os.name!='nt' else mode&0o444==0o444
    assert sorted(x.name for x in root.iterdir() if x.is_dir()) == ['manager', 'mcj_controller', 'mcj_minecraft']
    result = initializer.initialize(root, config, PASSWORD)
    assert result['accounts'] == 1 and result['runtime']['loader'] == 'NEOFORGE'
    assert result['public_access'] is False
    props = properties.loads((root / 'mcj_minecraft/data/server.properties').read_text())
    assert props['pause-when-empty-seconds'] == '0'
    assert props['online-mode'] == 'true' and props['force-gamemode'] == 'true'
    assert props['gamemode'] == 'spectator' and props['white-list'] == 'true'
    monkeypatch.setenv('MCJ_LAYOUT', 'services-v1')
    app = create_app(root=root, keyfile=root / 'manager/secrets/encryption',
                     origin=config['origin'], start_worker=False)
    client = TestClient(app, base_url=config['origin'],client=('127.0.0.1',50000))
    from test_security import post as security_post
    def post(client, path, data=None, csrf=None):
        return security_post(client, path, data, csrf, origin=config['origin'])
    login = post(client, '/api/auth/login', {'username': config['username'], 'password': PASSWORD})
    assert login.status_code == 200
    assert client.get('/api/overview').status_code == 403
    changed = post(client, '/api/auth/password', {'current': PASSWORD, 'password': 'Fixture-Changed-Password-2026!'}, login.json()['csrf'])
    assert changed.status_code == 200
    csrf = changed.json()['csrf']
    setup = post(client, '/api/auth/setup/totp', csrf=csrf)
    assert setup.status_code == 200
    factor = post(client, '/api/auth/setup/confirm', {'method': 'totp', 'challenge': setup.json()['challenge'],
                  'code': pyotp.TOTP(setup.json()['secret']).now()}, csrf)
    assert factor.status_code == 200
    assert client.get('/api/auth/me').json()['setup_wizard_pending'] is True
    assert client.get('/api/setup').json()['pending'] is True
    assert app.state.store.get('server')['loader_version'] == '26.3.0.99'
    assert app.state.store.get('smtp')['host'] == ''
    assert all(not app.state.store.get('release')[x] for x in
               ['public_web', 'public_game', 'visitor_verified', 'restore_verified', 'security_verified'])
    database = (root / 'manager/state/manager.sqlite3').read_bytes()
    before = hashlib.sha256(database).hexdigest()
    with pytest.raises(RuntimeError, match='installation_already_initialized'):
        initializer.initialize(root, config, PASSWORD)
    assert hashlib.sha256((root / 'manager/state/manager.sqlite3').read_bytes()).hexdigest() == before

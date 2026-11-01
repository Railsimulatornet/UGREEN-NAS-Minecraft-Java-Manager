"""Exercise hostile world files without starting a game or Docker container."""
import gzip
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mcj import worlds


ROOT = Path(__file__).resolve().parents[1]
LEVEL = b'\x0a\x00\x00\x0a\x00\x04Data\x03\x00\x0bDataVersion\x00\x00\x17\x70\x00\x00'


def test_regular_world_metadata_is_unchanged(tmp_path):
    path = tmp_path / 'level.dat'
    raw = gzip.compress(LEVEL)
    path.write_bytes(raw)
    assert worlds.validate_level(path) == 6000
    assert worlds.validate_level(path, metadata=True) == {'data_version': 6000, 'seed': None}
    assert path.read_bytes() == raw


@pytest.mark.skipif(os.name != 'posix', reason='Requires Linux no-follow semantics')
def test_level_symlink_is_rejected_without_reading_its_target(tmp_path):
    target = tmp_path / 'outside.dat'
    raw = gzip.compress(LEVEL)
    target.write_bytes(raw)
    path = tmp_path / 'level.dat'
    path.symlink_to(target)
    with pytest.raises(ValueError, match='world_level_dat_invalid'):
        worlds.validate_level(path)
    assert target.read_bytes() == raw and path.is_symlink()


FIFO_CHECK = r'''
import gzip, importlib, os, sys
from pathlib import Path
from types import SimpleNamespace
from mcj import worlds
from mcj.project_paths import project_path

root, method = Path(sys.argv[1]), sys.argv[2]
folder = project_path(root, 'server') / 'world'
folder.mkdir(parents=True)
os.mkfifo(folder / 'level.dat', 0o600)
if method == 'validate':
    try:
        worlds.validate_level(folder / 'level.dat')
    except ValueError as exc:
        assert str(exc) == 'world_level_dat_invalid'
    else:
        raise AssertionError('FIFO was accepted')
elif method == 'existing':
    from mcj.world_operations import existing
    try:
        existing(SimpleNamespace(ROOT=root), 'world')
    except ValueError as exc:
        assert str(exc) == 'world_level_dat_invalid'
    else:
        raise AssertionError('FIFO was accepted')
else:
    import docker
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient
    from mcj.store import Store
    secrets = project_path(root, 'secrets')
    secrets.mkdir(parents=True)
    key = secrets / 'encryption'
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    for name in ['rpc', 'rcon']:
        (secrets / name).write_text('disposable-' + name)
    os.environ.update(PROJECT_ROOT=str(root), BACKUP_ROOT=str(root / 'backups'),
                      RPC_SECRET=str(secrets / 'rpc'), RCON_SECRET=str(secrets / 'rcon'))
    class NoDocker:
        def __getattr__(self, name):
            raise AssertionError('No Docker operation may run')
    docker.from_env = lambda **kwargs: NoDocker()
    st = Store(project_path(root, 'state'), key)
    controller = importlib.import_module('mcj.controller')
    client = TestClient(controller.app, raise_server_exceptions=False)
    response = client.post('/world/operation',
        json={'operation': 'change', 'name': 'world', 'actor': 1},
        headers={'Authorization': 'Bearer disposable-rpc'})
    assert response.status_code == 503, response.text
    assert response.json()['reason'] == 'world_level_dat_invalid', response.text
    assert controller.LOCK.acquire(blocking=False), 'controller maintenance lock retained'
    controller.LOCK.release()
    with st.change_lock():
        pass
print('FIFO_REJECTED')
'''


@pytest.mark.skipif(os.name != 'posix' or not hasattr(os, 'mkfifo'), reason='Requires Linux FIFO semantics')
@pytest.mark.parametrize('layout', ['legacy', 'services-v1'])
@pytest.mark.parametrize('method', ['validate', 'existing', 'controller'])
def test_fifo_is_rejected_without_waiting_and_maintenance_locks_are_released(tmp_path, layout, method):
    environment = dict(os.environ, MCJ_LAYOUT=layout)
    environment['PYTHONPATH'] = str(ROOT) + os.pathsep + environment.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, '-c', FIFO_CHECK, str(tmp_path / 'project'), method],
                            env=environment, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == 'FIFO_REJECTED'


@pytest.mark.skipif(os.name != 'posix' or not hasattr(os, 'mkfifo'), reason='Requires Linux FIFO semantics')
def test_archive_forecast_rejects_fifo_before_opening_tar(tmp_path, monkeypatch):
    from mcj import storage_preflight
    path = tmp_path / 'archive.tar.gz'
    os.mkfifo(path, 0o600)
    def never_open(*args, **kwargs):
        raise AssertionError('Special files must be rejected before tarfile.open')
    monkeypatch.setattr(storage_preflight.tarfile, 'open', never_open)
    with pytest.raises(ValueError, match='storage_archive_unavailable'):
        storage_preflight.archive_size(path)

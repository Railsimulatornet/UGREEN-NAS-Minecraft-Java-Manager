"""Restore must detect an unusable project definition before stopping a server."""
from types import SimpleNamespace

import pytest

from mcj import maintenance


@pytest.mark.parametrize('reason', [
    'compose_configuration_failed',
    'compose_identity_mismatch',
    'compose_service_scope_mismatch',
])
def test_invalid_compose_blocks_restore_before_server_gate_or_backup(monkeypatch, tmp_path, reason):
    called = []
    state = SimpleNamespace(get=lambda key: {'container_memory_mb': 8192})
    monkeypatch.setattr(maintenance, 'store', lambda controller: state)
    monkeypatch.setattr(maintenance, 'require_runtime_consistency', lambda *args: None)
    monkeypatch.setattr(maintenance.storage_preflight, 'require', lambda *args: None)

    def compose():
        called.append('compose')
        raise RuntimeError(reason)

    def gate(*args):
        called.append('gate')
        pytest.fail('The running server must not enter maintenance with an invalid Compose definition')

    def backup(*args, **kwargs):
        called.append('backup')
        pytest.fail('No backup/stop/write is needed to discover unreadable project configuration')

    controller = SimpleNamespace(
        ROOT=tmp_path, BACKUPS=tmp_path / 'backups', compose_context=compose,
        checked_archive=lambda name: (tmp_path / 'backup.tar.gz', {'docker_image_id': 'sha256:' + 'a' * 64}, None),
    )
    monkeypatch.setattr(maintenance, 'idle_gate', gate)
    monkeypatch.setattr(maintenance, 'full_backup', backup)
    with pytest.raises(RuntimeError, match=reason):
        maintenance._apply_change(controller, 'restore', 1, archive='backup.tar.gz')
    assert called == ['compose']

import os
import stat

import pytest

from mcj.maintenance import restore_runtime


@pytest.mark.skipif(os.name == 'nt', reason='Linux runtime uses POSIX directory replacement and modes')
@pytest.mark.parametrize('mask',[0o022,0o077])
def test_restore_replaces_read_only_script_and_preserves_saved_mode(tmp_path,mask):
    previous=os.umask(mask)
    saved = tmp_path / 'saved'
    target = tmp_path / 'runtime'
    saved.mkdir()
    target.mkdir()
    original = saved / 'start.sh'
    original.write_bytes(b'#!/bin/sh\nexec old-server\n')
    original.chmod(0o550)
    current = target / 'start.sh'
    current.write_bytes(b'#!/bin/sh\nexec candidate-server\n')
    current.chmod(0o550)
    try:
        restore_runtime(saved, target)
        assert current.read_bytes() == original.read_bytes()
        assert stat.S_IMODE(current.stat().st_mode) == stat.S_IMODE(original.stat().st_mode)
    finally:
        current.chmod(0o600)
        original.chmod(0o600)
        os.umask(previous)


def test_restore_replaces_existing_file_bytes(tmp_path):
    saved = tmp_path / 'saved'
    target = tmp_path / 'runtime'
    saved.mkdir()
    target.mkdir()
    (saved / 'runtime.json').write_bytes(b'{"loader":"previous"}')
    (target / 'runtime.json').write_bytes(b'{"loader":"candidate"}')
    restore_runtime(saved, target)
    assert (target / 'runtime.json').read_bytes() == b'{"loader":"previous"}'


def test_restore_rejects_symlink_source(tmp_path):
    saved = tmp_path / 'saved'
    target = tmp_path / 'runtime'
    saved.mkdir()
    target.mkdir()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'not a saved runtime file')
    try:
        (saved / 'start.sh').symlink_to(outside)
    except OSError:
        pytest.skip('Symlink creation requires an enabled Windows privilege')
    with pytest.raises(RuntimeError, match='unsafe_rollback_runtime'):
        restore_runtime(saved, target)
    assert not (target / 'start.sh').exists()

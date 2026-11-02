import hashlib

import pytest

from mcj.isolated_runtime import start_script


@pytest.fixture
def legacy(tmp_path):
    library=tmp_path/'libraries/net/neoforged/forge/1.20.1-47.1.106/forge-1.20.1-47.1.106-universal.jar'
    library.parent.mkdir(parents=True);library.write_bytes(b'verified-loader')
    (tmp_path/'run.sh').write_text('#!/bin/sh\njava @user_jvm_args.txt @libraries/args.txt "$@"\n')
    config={'loader':'NEOFORGE','version':'1.20.1','loader_version':'47.1.106','loader_components':{
        'loader':'NEOFORGE','minecraft':'1.20.1','loader_version':'47.1.106',
        'sha256':hashlib.sha256(library.read_bytes()).hexdigest()}}
    return tmp_path,config,library


def test_legacy_offline_start_keeps_the_guard_and_property_checks(legacy):
    data,config,_=legacy
    prefix=b'#!/bin/bash\nset -euo pipefail\n(cd /data/mods && sha256sum --check /mcj/guard.sha256)\n'
    script=start_script(data,config,prefix+b'exec /start\n')
    assert script.startswith(prefix)
    assert script.endswith(b'export TYPE=CUSTOM\nexport CUSTOM_SERVER=/data/run.sh\nexport FAMILY=FORGE\nexec /start\n')
    assert config['loader']=='NEOFORGE'


@pytest.mark.parametrize('loader,version',[('FABRIC','1.20.1'),('FORGE','1.20.1'),('NEOFORGE','1.21.1'),('NEOFORGE','26.3')])
def test_other_installed_runtimes_keep_the_exact_existing_script(tmp_path,loader,version):
    script=b'#!/bin/bash\r\nexec /start\r\n'
    assert start_script(tmp_path,{'loader':loader,'version':version},script)==script


def test_legacy_offline_start_rejects_changed_loader_bytes(legacy):
    data,config,library=legacy;library.write_bytes(b'different-loader')
    with pytest.raises(ValueError,match='loader_runtime_hash_mismatch'):
        start_script(data,config,b'exec /start\n')


@pytest.mark.parametrize('state',['missing','directory','empty','oversize','link'])
def test_legacy_offline_start_rejects_invalid_launcher(legacy,state):
    data,config,_=legacy;launcher=data/'run.sh';launcher.unlink()
    if state=='directory':launcher.mkdir()
    elif state=='empty':launcher.write_bytes(b'')
    elif state=='oversize':launcher.write_bytes(b'x'*65537)
    elif state=='link':
        outside=data.parent/(data.name+'-outside');outside.write_bytes(b'outside')
        try:launcher.symlink_to(outside)
        except OSError:pytest.skip('Symbolic links require an enabled Windows privilege')
    with pytest.raises(ValueError,match='isolated_runtime_launcher_invalid'):
        start_script(data,config,b'exec /start\n')


def test_legacy_offline_start_rejects_unknown_startup_template(legacy):
    data,config,_=legacy
    with pytest.raises(ValueError,match='isolated_runtime_start_script_invalid'):
        start_script(data,config,b'exec other-start\n')

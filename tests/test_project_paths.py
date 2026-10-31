import io,json,zipfile
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from mcj.project_paths import project_path,SERVICE_PATHS
from mcj.store import Store
from mcj import mods


@pytest.mark.parametrize('relative',['state/manager.sqlite3','staging/file.jar','server/world/level.dat',
    'control/runtime/runtime.json','releases/guards/registry.json','.restore-tests/example','secrets/rcon'])
def test_layout_is_explicit_and_legacy_paths_stay_unchanged(tmp_path,monkeypatch,relative):
    monkeypatch.delenv('MCJ_LAYOUT',raising=False)
    assert project_path(tmp_path,relative)==tmp_path/relative
    head,*tail=relative.split('/')
    assert project_path(tmp_path,relative,'services-v1')==tmp_path/SERVICE_PATHS[head]/Path(*tail)


@pytest.mark.parametrize('value',['../outside','server/../../outside','/etc/passwd',r'server\..\outside','C:/outside',''])
def test_unsafe_logical_paths_are_rejected(tmp_path,value):
    with pytest.raises(ValueError,match='unsafe_project_path'):project_path(tmp_path,value,'services-v1')


def test_unknown_layout_cannot_silently_write_into_legacy_paths(tmp_path,monkeypatch):
    monkeypatch.setenv('MCJ_LAYOUT','typo')
    with pytest.raises(ValueError,match='unknown_project_layout'):project_path(tmp_path,'state')


def test_mod_upload_and_manual_drop_use_organized_paths(tmp_path,monkeypatch):
    monkeypatch.setenv('MCJ_LAYOUT','services-v1')
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    st=Store(project_path(tmp_path,'state'),key)
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:z.writestr('fabric.mod.json',json.dumps({'id':'layout_probe','version':'1.0'}))
    record=mods.stage(st,tmp_path,raw.getvalue(),'probe.jar')
    assert (tmp_path/'manager/staging'/(record['id']+'.jar')).is_file()
    drop=project_path(tmp_path,'mods');drop.mkdir(parents=True)
    (drop/'probe.jar').write_bytes(raw.getvalue());mods.scan_drop_folder(st,tmp_path)
    assert not (tmp_path/'staging').exists() and not (tmp_path/'state').exists()
    assert (tmp_path/'manager/state/manager.sqlite3').is_file()

import hashlib
import json
import re
from pathlib import Path
import pytest
from mcj.guard_artifacts import restore_current_guard
from mcj.project_paths import project_path


@pytest.mark.parametrize('manifest,source',[('guard.json','guard-neoforge'),('guard-neoforge-1211.json','guard-neoforge-1211')])
def test_release_guard_identity_matches_build_manifest_and_embedded_metadata(manifest,source):
    from mcj.mods import inspect_jar
    root=Path(__file__).resolve().parents[1]
    entry=json.loads((root/'artifacts'/manifest).read_text(encoding='utf-8'))
    raw=(root/'artifacts'/entry['filename']).read_bytes()
    build_version=re.search(r"^version='([^']+)'",(root/source/'build.gradle').read_text(),re.M)[1]
    actual=inspect_jar(raw)
    assert hashlib.sha256(raw).hexdigest()==entry['sha256']
    assert entry['version']==build_version==actual['mods'][0]['version']
    assert actual['loader']==entry['loader']=='NEOFORGE'
    assert actual['mods'][0]['id']=='mcj_guard'
    assert entry['metadata']==actual


def fixture(tmp_path):
    data=tmp_path/'candidate';(data/'mods').mkdir(parents=True)
    old={'filename':'guard-old.jar','sha256':hashlib.sha256(b'known-old').hexdigest(),'minecraft':'26.3','loader':'NEOFORGE','dependencies':[]}
    active={'filename':'guard-current.jar','sha256':hashlib.sha256(b'known-current').hexdigest(),'minecraft':'26.3','loader':'NEOFORGE',
            'path':'releases/guards/guard-current.jar','dependencies':[]}
    source=project_path(tmp_path,active['path']);source.parent.mkdir(parents=True);source.write_bytes(b'known-current')
    (data/'mods'/old['filename']).write_bytes(b'known-old')
    return data,old,active


@pytest.mark.parametrize('layout',['legacy','services-v1'])
def test_known_old_backup_uses_current_guard_before_any_native_execution(tmp_path,monkeypatch,layout):
    monkeypatch.setenv('MCJ_LAYOUT',layout);data,old,active=fixture(tmp_path)
    assert restore_current_guard(tmp_path,data,old,active,[old])==active
    assert not (data/'mods/guard-old.jar').exists()
    assert (data/'mods/guard-current.jar').read_bytes()==b'known-current'


@pytest.mark.parametrize('condition',['unknown','tampered_old','tampered_current','conflict','traversal'])
def test_unknown_or_changed_artifacts_cannot_be_restored_or_overwrite_mods(tmp_path,condition):
    data,old,active=fixture(tmp_path);retained=[old]
    if condition=='unknown':retained=[]
    if condition=='tampered_old':(data/'mods/guard-old.jar').write_bytes(b'changed')
    if condition=='tampered_current':project_path(tmp_path,active['path']).write_bytes(b'changed')
    if condition=='conflict':(data/'mods/guard-current.jar').write_bytes(b'own mod')
    if condition=='traversal':active['path']='../outside.jar'
    with pytest.raises((RuntimeError,ValueError)):restore_current_guard(tmp_path,data,old,active,retained)
    assert (data/'mods/guard-old.jar').exists()

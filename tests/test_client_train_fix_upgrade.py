import copy
import hashlib
import pytest
from mcj import client_packs as cp,client_train_fix as train,mods
from test_client_train_fix import create_record


@pytest.mark.parametrize('checksum',list(train.ARTIFACTS))
def test_explicit_old_and_new_pins_export_exactly_one_matching_file(checksum):
    graphics={'train_compatibility_patch':checksum};before=copy.deepcopy(graphics)
    selected=[create_record()];report=[];bundled={}
    train.bundle(graphics,train.RUNTIME,selected,report,bundled)
    version,filename=train.ARTIFACTS[checksum]
    jars=[k for k in bundled if k.startswith('overrides/mods/')]
    assert jars==['overrides/mods/'+filename]
    assert hashlib.sha256(bundled[jars[0]]).hexdigest()==checksum
    assert selected[-1]['metadata']['mods'][0]['version']==version
    assert report[-1]['client']=='required' and report[-1]['sha256']==checksum
    assert len(bundled)==3 and graphics==before


@pytest.mark.parametrize('broken',['artifact','metadata','notice'])
def test_failure_never_partially_changes_archive_selection(monkeypatch,broken):
    selected=[create_record()];before=copy.deepcopy(selected);report=[];bundled={}
    reader=cp.read_bounded
    if broken=='metadata':
        monkeypatch.setattr(mods,'inspect_jar',lambda raw:{'mods':[]})
    else:
        def read(path,limit):
            if broken=='artifact' and path.name==train.FILENAME:return b'corrupt'
            if broken=='notice' and path.name.endswith('-NOTICE.txt'):raise ValueError('missing_notice')
            return reader(path,limit)
        monkeypatch.setattr(cp,'read_bounded',read)
    with pytest.raises(ValueError):train.bundle({'train_compatibility_patch':train.SHA256},train.RUNTIME,selected,report,bundled)
    assert selected==before and not report and not bundled


def test_published_observer_jar_matches_its_source_and_full_copyright():
    from pathlib import Path
    import zipfile
    root=Path(__file__).parents[1]
    with zipfile.ZipFile(root/'mcj/client_pack_resources'/train.FILENAME)as jar:
        assert b'Copyright (c) 2026 Roman Glos' in jar.read('LICENSE')
        source=root/'docs/compatibility/create-trains/position-sync-1.0.5'
        for path in source.glob('*.java'):
            assert jar.read('META-INF/sources/'+path.name)==path.read_bytes()

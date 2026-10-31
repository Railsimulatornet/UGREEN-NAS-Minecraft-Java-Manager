import gzip,io,json,zipfile,struct
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from mcj import worlds,mods
from mcj.store import Store


def setup(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    return Store(tmp_path/'state',key)


def world_zip(path,files=None):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('Testwelt/level.dat',gzip.compress(b'\x0a\x00\x00\x0a\x00\x04Data\x03\x00\x0bDataVersion\x00\x00\x17\x70\x00\x00'))
        z.writestr('Testwelt/region/r.0.0.mca',b'unchanged world region')
        z.writestr('Testwelt/session.lock',b'temporary lock is not imported')
        for name,value in (files or {}).items():z.writestr(name,value)
    return path


def test_import_is_staged_and_only_copied_to_candidate_with_hash_verification(tmp_path):
    store=setup(tmp_path);archive=world_zip(tmp_path/'world.zip');before=mods.fingerprint(store)
    record=worlds.stage(store,tmp_path,archive,'Importiert')
    assert record['files']==2 and not record['live_server_changed']
    assert mods.fingerprint(store)!=before and not (tmp_path/'server').exists()
    data=tmp_path/'candidate';data.mkdir()
    assert worlds.apply_import(store,tmp_path,data,{'world':'Importiert'})['files']==2
    assert (data/'Importiert/region/r.0.0.mca').read_bytes()==b'unchanged world region'
    assert not (data/'Importiert/session.lock').exists()
    source=tmp_path/'staging/worlds'/record['id']/'data/region/r.0.0.mca';source.write_bytes(b'tampered')
    second=tmp_path/'second-candidate';second.mkdir()
    with pytest.raises(ValueError,match='world_staging_integrity_failed'):
        worlds.apply_import(store,tmp_path,second,{'world':'Importiert'})


@pytest.mark.parametrize('name',['../escape','/absolute','a:b','Testwelt/../../escape','Testwelt\\..\\..\\escape'])
def test_unsafe_archive_cannot_write_outside_staging(tmp_path,name):
    store=setup(tmp_path);archive=world_zip(tmp_path/'world.zip',{name:b'unsafe'})
    with pytest.raises(ValueError,match='world_archive_unsafe_path'):worlds.stage(store,tmp_path,archive,'Importiert')
    assert not list((tmp_path/'staging/worlds').iterdir()) and not store.get('world_imports')


def test_existing_world_is_never_overwritten_by_import(tmp_path):
    store=setup(tmp_path);archive=world_zip(tmp_path/'world.zip');worlds.stage(store,tmp_path,archive,'Importiert')
    data=tmp_path/'candidate';(data/'Importiert').mkdir(parents=True)
    (data/'Importiert/level.dat').write_bytes(b'existing world')
    assert worlds.apply_import(store,tmp_path,data,{'world':'Importiert'}) is None
    assert (data/'Importiert/level.dat').read_bytes()==b'existing world'


def test_newer_world_is_rejected_before_a_version_change_can_start_it(tmp_path):
    data=tmp_path/'candidate';path=data/'world_263/level.dat';path.parent.mkdir(parents=True)
    raw=gzip.compress(b'\x0a\x00\x00\x0a\x00\x04Data\x03\x00\x0bDataVersion'+struct.pack('>i',5023)+b'\x00\x00')
    path.write_bytes(raw)
    with pytest.raises(ValueError,match='world_newer_than_selected_server'):
        worlds.require_supported_format(data,{'world':'world_263'},{'minecraft_data_version':3955})
    assert path.read_bytes()==raw
    worlds.require_supported_format(data,{'world':'world_263'},{'minecraft_data_version':5023})
    worlds.require_supported_format(data,{'world':'fresh_world'},{'minecraft_data_version':3955})
    with pytest.raises(ValueError,match='world_version_unverified'):
        worlds.require_supported_format(data,{'world':'world_263'},{})


def test_two_world_roots_and_symlinks_rejected(tmp_path):
    store=setup(tmp_path);archive=world_zip(tmp_path/'world.zip',{'Other/level.dat':gzip.compress(b'\x0a\0\0\0')})
    with pytest.raises(ValueError,match='world_archive_layout_invalid'):worlds.stage(store,tmp_path,archive,'Importiert')
    archive=world_zip(tmp_path/'linked.zip')
    with zipfile.ZipFile(archive,'a') as z:
        info=zipfile.ZipInfo('Testwelt/linked');info.create_system=3;info.external_attr=0o120777<<16;z.writestr(info,'/etc/passwd')
    with pytest.raises(ValueError,match='world_archive_unsafe_path'):worlds.stage(store,tmp_path,archive,'Importiert')


def test_inventory_has_actual_names_and_sizes(tmp_path):
    root=tmp_path/'server';(root/'world/region').mkdir(parents=True)
    (root/'world/level.dat').write_bytes(b'level');(root/'world/region/r.0.0.mca').write_bytes(b'region')
    assert worlds.inventory(root)==[{'name':'world','size':11,'size_complete':True,'source':'server','seed':None}]


@pytest.mark.parametrize('raw',[b'',b'\x0a\x00\x00\x00',b'\x0a\x00\x00\x07\x00\x01a\xff\xff\xff\xff',b'\x0a\x00\x00\x0a\x00\x04Data'])
def test_invalid_truncated_or_negative_length_nbt_is_rejected(tmp_path,raw):
    path=tmp_path/'level.dat';path.write_bytes(gzip.compress(raw))
    with pytest.raises(ValueError,match='world_level_dat_invalid'):worlds.validate_level(path)

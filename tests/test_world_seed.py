import gzip,struct,zipfile
import pytest
from mcj import worlds

def tag(kind,name,payload):
    encoded=name.encode();return bytes([kind])+struct.pack('>H',len(encoded))+encoded+payload

def level(tmp_path,seed,modern=True,extra=b''):
    value=tag(4,'seed' if modern else 'RandomSeed',struct.pack('>q',seed))
    if modern:value=tag(10,'WorldGenSettings',value+b'\x00')
    data=tag(3,'DataVersion',struct.pack('>i',6000))+value+extra+b'\x00'
    path=tmp_path/'level.dat';path.write_bytes(gzip.compress(b'\x0a\x00\x00'+tag(10,'Data',data)+b'\x00'))
    return path

@pytest.mark.parametrize('seed',[0,-1,9223372036854775807,-9223372036854775808,9007199254740993])
@pytest.mark.parametrize('modern',[True,False])
def test_real_saved_seed_is_a_lossless_decimal_string(tmp_path,seed,modern):
    path=level(tmp_path,seed,modern,tag(10,'ModData',tag(4,'seed',struct.pack('>q',123))+b'\x00'))
    assert worlds.validate_level(path)==6000
    assert worlds.validate_level(path,metadata=True)['seed']==str(seed)

def test_mod_seed_does_not_replace_world_seed_and_inventory_is_read_only(tmp_path):
    world=tmp_path/'world';world.mkdir();path=level(world,9007199254740993)
    before=path.read_bytes();result=worlds.inventory(tmp_path)
    assert result[0]['seed']=='9007199254740993'
    assert path.read_bytes()==before
    path.write_bytes(b'invalid gzip')
    assert worlds.inventory(tmp_path)[0]['seed'] is None

def test_seed_with_wrong_nbt_type_or_missing_tag_is_unavailable(tmp_path):
    data=tag(3,'DataVersion',struct.pack('>i',6000))+tag(10,'WorldGenSettings',tag(3,'seed',struct.pack('>i',7))+b'\x00')+b'\x00'
    path=tmp_path/'level.dat';path.write_bytes(gzip.compress(b'\x0a\x00\x00'+tag(10,'Data',data)+b'\x00'))
    assert worlds.validate_level(path,metadata=True)['seed'] is None

def test_new_world_storage_takes_priority_over_legacy_metadata(tmp_path):
    level(tmp_path,123)
    folder=tmp_path/'data/minecraft';folder.mkdir(parents=True)
    path=folder/'world_gen_settings.dat'
    data=tag(3,'DataVersion',struct.pack('>i',5023))+tag(10,'data',tag(4,'seed',struct.pack('>q',-9223372036854775808))+b'\x00')+b'\x00'
    path.write_bytes(gzip.compress(b'\x0a\x00\x00'+data))
    assert worlds.world_seed(tmp_path)=='-9223372036854775808'
    path.write_bytes(b'broken')
    assert worlds.world_seed(tmp_path) is None


@pytest.mark.parametrize('seed',[-9223372036854775808,9223372036854775807,9007199254740993])
@pytest.mark.parametrize('separate_generation',[False,True])
def test_first_and_cached_world_import_preserve_the_exact_seed(tmp_path,seed,separate_generation):
    from test_worlds import setup
    store=setup(tmp_path)
    source=tmp_path/'source';source.mkdir();level(source,123 if separate_generation else seed)
    if separate_generation:
        folder=source/'data/minecraft';folder.mkdir(parents=True)
        data=tag(3,'DataVersion',struct.pack('>i',5023))+tag(10,'data',tag(4,'seed',struct.pack('>q',seed))+b'\x00')+b'\x00'
        (folder/'world_gen_settings.dat').write_bytes(gzip.compress(b'\x0a\x00\x00'+data))
    archive=tmp_path/'import.zip'
    with zipfile.ZipFile(archive,'w') as output:
        for path in source.rglob('*'):
            if path.is_file():output.write(path,str(path.relative_to(source)).replace('\\','/'))
    for name in ('FirstImport','CachedImport'):
        result=worlds.stage(store,tmp_path,archive,name)
        assert result['seed']==str(seed)
        assert next(x for x in store.get('world_imports') if x['name']==name)['seed']==str(seed)
    assert not (tmp_path/'server').exists()

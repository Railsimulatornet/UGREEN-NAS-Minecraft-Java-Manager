import io,json,zipfile
import pytest
from mcj.mods import inspect_jar

def archive(entries):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        for name,value in entries.items():z.writestr(name,value)
    return stream.getvalue()

MOD='modLoader="javafml"\n[[mods]]\nmodId="create"\nversion="6.0.11-adapted-1.31"\n'

def test_flat_license_resource_is_allowed_without_extracting_or_repacking():
    raw=archive({'META-INF/neoforge.mods.toml':MOD,'Create: Adapted_LICENSE.md':'MIT'})
    result=inspect_jar(raw)
    assert result['loader']=='NEOFORGE' and result['mods'][0]['id']=='create'
    import hashlib
    assert result['sha256']==hashlib.sha256(raw).hexdigest()

@pytest.mark.parametrize('name',['C:LICENSE.md','C:/escape','a:b.class','../Create: Adapted_LICENSE.md','LICENSE.md:stream'])
def test_drive_paths_traversal_and_ads_remain_blocked(name):
    with pytest.raises(ValueError,match='jar_unsafe_path'):inspect_jar(archive({'META-INF/neoforge.mods.toml':MOD,name:'data'}))

def test_neoforge_bundled_mods_and_plain_libraries_are_distinguished():
    child=archive({'META-INF/neoforge.mods.toml':MOD.replace('create','ponder')})
    library=archive({'META-INF/MANIFEST.MF':'Manifest-Version: 1.0\n'})
    definition={'jars':[{'path':'META-INF/jarjar/ponder.jar'},
        {'path':'META-INF/jarjar/library.jar','identifier':{'group':'example','artifact':'Registrate'},'version':{'artifactVersion':'1.2.3'}}]}
    result=inspect_jar(archive({'META-INF/neoforge.mods.toml':MOD,'META-INF/jarjar/metadata.json':json.dumps(definition),
        'META-INF/jarjar/ponder.jar':child,'META-INF/jarjar/library.jar':library}))
    assert result['embedded'][0]['mods'][0]['id']=='ponder'
    assert result['embedded_libraries'][0]['artifact']=='Registrate'

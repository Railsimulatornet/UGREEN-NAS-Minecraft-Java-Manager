import hashlib
import io
import json
import os
import zipfile

from cryptography.fernet import Fernet
import httpx
import pytest

from mcj import client_packs, loader_catalogs, mods, versions
from mcj.store import Store


@pytest.fixture
def store(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    return Store(tmp_path/'state',key)


def jar(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for name,value in files.items():archive.writestr(name,value)
    return stream.getvalue()


def fixture(loader='FORGE',minecraft='1.20.1',version='47.4.28'):
    expected=loader_catalogs.identity(loader,minecraft,version)
    universal=jar({'META-INF/mods.toml':'license="LGPL"\n[[mods]]\nmodId="forge"\nversion="${global.forgeVersion}"\n'})
    artifact={'url':expected['source'],'path':expected['library_path'],
              'sha1':hashlib.sha1(universal).hexdigest(),'size':len(universal)}
    library={'name':expected['coordinate'],'downloads':{'artifact':artifact}}
    profile={'minecraft':minecraft,'version':expected['id'],'libraries':[library]}
    version_json={'id':expected['id'],'inheritsFrom':minecraft,'libraries':[library]}
    return expected,universal,profile,version_json


@pytest.mark.parametrize('loader,minecraft,version',[
    ('FORGE','1.20.1','47.4.28'),('FORGE','1.21.1','52.1.20'),
    ('FORGE','26.3','66.1.0'),('NEOFORGE','1.20.1','47.1.106'),
])
def test_installer_binds_the_exact_universal_and_runtime_file(store,tmp_path,loader,minecraft,version):
    expected,universal,profile,version_json=fixture(loader,minecraft,version)
    installer=jar({'install_profile.json':json.dumps(profile),'version.json':json.dumps(version_json)})
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200,content={expected['installer']:installer,expected['source']:universal}[str(request.url)])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        proof=loader_catalogs.ensure_components(store,loader,minecraft,version,client)
        assert loader_catalogs.ensure_components(store,loader,minecraft,version,client)==proof
    assert calls==[expected['installer'],expected['source']]
    assert proof['installer_sha256']==hashlib.sha256(installer).hexdigest()
    runtime={'version':minecraft,'loader':loader,'loader_version':version,'loader_components':{'sha256':'forged'}}
    selected=versions.runtime_components(store,runtime)
    assert selected['loader_components']==proof
    path=tmp_path/'server/libraries'/expected['library_path']
    path.parent.mkdir(parents=True);path.write_bytes(universal)
    loader_catalogs.verify_runtime(tmp_path/'server',selected)
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='loader_runtime_hash_mismatch'):
        loader_catalogs.verify_runtime(tmp_path/'server',selected)


@pytest.mark.parametrize('change',[
    'wrong_minecraft','wrong_version','wrong_coordinate','host','traversal','checksum','size','conflicting_library',
])
def test_installer_identity_and_hash_changes_never_enter_the_cache(store,change):
    expected,universal,profile,version_json=fixture()
    artifact=profile['libraries'][0]['downloads']['artifact']
    if change=='wrong_minecraft':profile['minecraft']='1.21.1'
    elif change=='wrong_version':version_json['id']='1.20.1-forge-47.4.29'
    elif change=='wrong_coordinate':profile['libraries'][0]['name']='net.other:forge:1.20.1-47.4.28:universal'
    elif change=='host':artifact['url']='https://untrusted.invalid/forge.jar'
    elif change=='traversal':artifact['path']='../../forge.jar'
    elif change=='checksum':artifact['sha1']='0'*40
    elif change=='size':artifact['size']+=1
    elif change=='conflicting_library':
        version_json=json.loads(json.dumps(version_json))
        version_json['libraries'][0]['downloads']['artifact']['sha1']='1'*40
    installer=jar({'install_profile.json':json.dumps(profile),'version.json':json.dumps(version_json)})
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=installer if str(request.url)==expected['installer'] else universal))) as client:
        with pytest.raises(ValueError,match='loader_metadata_'):
            loader_catalogs.ensure_components(store,'FORGE','1.20.1','47.4.28',client)
    assert not store.get('loader_components')


@pytest.mark.parametrize('minecraft,version',[
    ('../1.20.1','47.4.28'),('1.20.1','/etc/passwd'),('1.20.1','47.4.28/../../x'),
    ('1.20.1','https://untrusted.invalid'),('1.20.1','47.4.28-beta'),
])
def test_untrusted_runtime_cannot_choose_downloads_or_cache_paths(store,minecraft,version):
    with pytest.raises(ValueError):
        loader_catalogs.ensure_components(store,'FORGE',minecraft,version)
    assert not store.get('loader_components')


@pytest.mark.parametrize('loader,group',[('FORGE','net.minecraftforge'),('NEOFORGE','net.neoforged')])
def test_stable_forge_catalogue_requires_exact_game_and_artifact_identity(loader,group):
    xml=('<metadata><groupId>'+group+'</groupId><artifactId>forge</artifactId><versioning><versions>'
         '<version>1.20.1-47.1.106</version><version>1.20.1-47.4.28</version>'
         '<version>1.20.2-48.0.1</version><version>1.20.1-47.5.0-beta</version>'
         '</versions></versioning></metadata>').encode()
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=xml))) as client:
        assert loader_catalogs.available(client,loader,'1.20.1')==['47.4.28','47.1.106']
        assert loader_catalogs.available(client,loader,'1.20.1')==['47.4.28','47.1.106']
    xml=xml.replace(b'<artifactId>forge',b'<artifactId>other')
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=xml))) as client:
        with pytest.raises(ValueError,match='identity'):loader_catalogs.available(client,loader,'1.20.1')


@pytest.mark.parametrize('encoding',['utf-8','utf-16'])
def test_forge_catalogue_rejects_entity_expansion(encoding):
    xml=('<?xml version="1.0" encoding="'+encoding+'"?><!DOCTYPE metadata [<!ENTITY a "b">]>'
         '<metadata><groupId>net.minecraftforge</groupId><artifactId>forge</artifactId></metadata>').encode(encoding)
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=xml))) as client:
        with pytest.raises(ValueError,match='version_metadata_limit'):loader_catalogs.available(client,'FORGE','1.20.1')


def test_loader_download_limits_and_redirects_stop_before_inspection():
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(100):yield b'x'*65536
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Stream()))) as client:
        with pytest.raises(ValueError,match='loader_metadata_limit'):loader_catalogs.available(client,'FORGE','1.20.1')
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(302,headers={'Location':'https://untrusted.invalid/'}))) as client:
        with pytest.raises((ValueError,httpx.HTTPStatusError)):loader_catalogs.available(client,'FORGE','1.20.1')


def test_legacy_neoforge_uses_forge_mods_without_relaxing_modern_neoforge():
    meta={'loader':'FORGE','mods':[{'id':'example','version':'1.0'}],
          'dependencies':[{'id':'forge','range':'[47.1,48)','mandatory':True}],'client_only_hint':False}
    server={'version':'1.20.1','loader':'NEOFORGE','loader_version':'47.1.106','java':17}
    record={'id':'example','filename':'example.jar','metadata':meta}
    assert mods.dependency_report([record],server)['structural_checks']=='passed'
    assert not client_packs.dependency_check([record],server)
    for minecraft,version,java in [('1.21.1','21.1.265',21),('26.3','26.3.0.99',25)]:
        modern={**server,'version':minecraft,'loader_version':version,'java':java}
        assert any(item['issue']=='loader_mismatch' for item in mods.dependency_report([record],modern)['issues'])
        assert any(item['reason']=='loader_mismatch' for item in client_packs.dependency_check([record],modern))


def test_legacy_neoforge_never_falls_through_to_modern_coordinates():
    with pytest.raises(ValueError):loader_catalogs.identity('NEOFORGE','1.21.1','47.1.106')


@pytest.mark.skipif(os.name!='posix',reason='Production Linux symlink boundary')
def test_installed_loader_cannot_redirect_the_hash_check_through_a_directory_link(tmp_path):
    expected=loader_catalogs.identity('FORGE','1.20.1','47.4.28')
    outside=tmp_path/'outside';outside.mkdir();raw=b'known loader bytes'
    directory=tmp_path/'data/libraries/net/minecraftforge';directory.parent.mkdir(parents=True)
    directory.symlink_to(outside,target_is_directory=True)
    path=tmp_path/'data/libraries'/expected['library_path'];path.parent.mkdir(parents=True);path.write_bytes(raw)
    config={'loader':'FORGE','version':'1.20.1','loader_version':'47.4.28','loader_components':{
        'loader':'FORGE','minecraft':'1.20.1','loader_version':'47.4.28','sha256':hashlib.sha256(raw).hexdigest()}}
    with pytest.raises(ValueError,match='loader_runtime_hash_mismatch'):loader_catalogs.verify_runtime(tmp_path/'data',config)


@pytest.mark.skipif(os.name!='posix',reason='Production Linux symlink boundary')
def test_official_loader_cache_cannot_write_through_a_directory_link(store,tmp_path):
    outside=tmp_path/'outside';outside.mkdir();(store.state/'loader-cache').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='loader_runtime_hash_mismatch'):
        loader_catalogs.ensure_components(store,'FORGE','1.20.1','47.4.28')
    assert not list(outside.iterdir())


def test_fabric_client_export_checks_the_components_supplied_by_its_exact_loader():
    record={'filename':'example.jar','metadata':{'loader':'FABRIC','mods':[{'id':'example','version':'1.0'}],
            'dependencies':[{'id':'mixinextras','range':'>=0.5.0','mandatory':True}]}}
    active={'version':'26.3','java':25,'loader':'FABRIC','loader_version':'0.20.1'}
    assert client_packs.dependency_check([record],active)
    proof={'loader_version':'0.20.1','sha256':'a'*64,'components':{'fabricloader':'0.20.1','mixinextras':'0.5.5'}}
    assert not client_packs.dependency_check([record],{**active,'loader_components':proof})
    proof['loader_version']='0.20.2'
    assert client_packs.dependency_check([record],{**active,'loader_components':proof})


def test_forge_jarjar_can_read_a_bounded_library_from_the_official_meta_inf_jars_layout():
    library=jar({'example.txt':'library fixture'})
    bridge=jar({'META-INF/mods.toml':'license="MIT"\n[[mods]]\nmodId="bridge"\nversion="1.0"\n',
                'META-INF/jars/library.jar':library,
                'META-INF/jarjar/metadata.json':json.dumps({'jars':[{'identifier':{'group':'example','artifact':'library'},
                    'version':{'artifactVersion':'1.0'},'path':'META-INF/jars/library.jar'}]})})
    meta=mods.inspect_jar(bridge)
    assert meta['embedded_libraries']==[{'group':'example','artifact':'library','version':'1.0','sha256':hashlib.sha256(library).hexdigest()}]
    unsafe=jar({'META-INF/mods.toml':'license="MIT"\n[[mods]]\nmodId="bridge"\nversion="1.0"\n',
                'other/library.jar':library,
                'META-INF/jarjar/metadata.json':json.dumps({'jars':[{'identifier':{'group':'example','artifact':'library'},
                    'version':{'artifactVersion':'1.0'},'path':'other/library.jar'}]})})
    with pytest.raises(ValueError,match='jar_nested_file_invalid'):mods.inspect_jar(unsafe)


def test_forge_plan_defaults_to_the_accepted_loader_instead_of_catalogue_latest(store,monkeypatch):
    store.set('server',{**store.get('server'),'version':'1.20.1','loader':'FORGE','java':17,'loader_version':'47.4.28'})
    store.set('version_catalog',{'releases':[{'id':'1.20.1','url':'https://piston-meta.mojang.com/v1/packages/'+'a'*40+'/1.20.1.json','sha1':'unused'}]})
    guard={'minecraft':'1.20.1','loader':'FORGE','sha256':'b'*64,'java':17,'tested_loaders':['47.4.28'],
           'runtime_test':'passed','visitor_verified':True,'visitor_client_test':'passed'}
    store.set('guard_catalog',{'artifacts':[guard]})
    monkeypatch.setattr(versions,'read_json',lambda *args:{'id':'1.20.1','type':'release','javaVersion':{'majorVersion':17}})
    monkeypatch.setattr(loader_catalogs,'available',lambda *args:['47.5.0','47.4.28'])
    monkeypatch.setattr(loader_catalogs,'ensure_components',lambda *args:{'loader':'FORGE','loader_version':args[3]})
    selected={'version':'1.20.1','loader':'FORGE','loader_version':'','java':17}
    report=versions.check(store,selected,[])
    assert report['metadata_checks']=='passed' and report['configuration']['loader_version']=='47.4.28'
    assert report['runtime_test']=='not_tested' and report['visitor_client_test']=='not_verified'
    blocked=versions.check(store,{**selected,'loader_version':'47.5.0'},[])
    assert any(item['issue']=='guard_runtime_combination_not_tested' for item in blocked['issues'])
    store.set('guard_catalog',{'artifacts':[]})
    blocked=versions.check(store,selected,[])
    assert any(item['issue']=='visitor_guard_adapter_missing' for item in blocked['issues'])

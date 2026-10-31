import hashlib,io,json,zipfile
import httpx,pytest
from cryptography.fernet import Fernet
from mcj import mods,versions
from mcj.maven_ranges import matches
from mcj.store import Store


@pytest.mark.parametrize('actual,requirement,expected',[
 ('26.3','[26.3]',True),('26.4','[26.3]',False),('26.3.0','[26.3]',True),
 ('26.3','[26.3, 26.4)',True),('26.4','[26.3,26.4)',False),
 ('26.3','(26.3,26.4)',False),('26.4','(26.3,26.4]',True),
 ('26.3.0.97','[26.3.0.22-beta,26.4)',True),
 ('26.3.0.22-beta','[26.3.0.22,)',False),('1.0.0-rc.2','(1.0.0-rc.1,1.0.0)',True),
 ('0.6.6','[0.6.3,1.0.0)',True),('1.0.0','[0.6.3,1.0.0)',False),
 ('2.0','(,1.0],[2.0,)',True),('1.5','(,1.0],[2.0,)',False),
 ('1.5','(,1.0],[3.0,2.0)',None),('1.5','[2.0,1.0)',None),
 ('26.3','26.2',True),('26.3','',True),('26.3','>=26.2',None),
 ('26.3','[26.3',None),('26.3','(26.3)',None),('26.3','[26.3,26.3)',None),
 ('26.3','[26.3]trailing',None),('26.3','[26 .3]',None),
 ('1.0.0-mcj.1','[1.0,)',None),('1.0.0-mcj.1','[1.0.0-mcj.1]',True),
 ('1.0.100046-adapted-fork-early+mc26.3','[1.0.82,)',True),
 ('6.0.11-adapted-1.31','[6.0.11,)',None),('6.0.11-adapted-1.31','[6.0.0,7.0)',True),
 ('6.0.11-adapted-1.31','[1.19,2.0),[6.0.11-adapted-1.19,)',True),
 ('6.0.11-adapted-1.19','[1.19,2.0),[6.0.11-adapted-1.19,)',True),
 ('6.0.11-adapted-1.18','[1.19,2.0),[6.0.11-adapted-1.19,)',False),
 ('6.0.11-adapted-1.9','[6.0.11-adapted-1.19,)',False),
 ('6.0.11-adapted-1.100','[6.0.11-adapted-1.19,)',True),
 ('6.0.11-ADAPTED-1.31','[6.0.11-adapted-1.19,)',True),
 ('6.0.11-other-1.31','[6.0.11-adapted-1.19,)',None),
 ('6.0.11-adapted-1.31-beta','[6.0.11-adapted-1.19,)',None),
 ('6.0.11-adapted-1.31','[6.0.11-adapted-1.31,6.0.11-adapted-1.32)',True),
 ('1.0.0','[1.0.0-ga]',True),('1.0.0-sp1','(1.0,)',True),
])
def test_maven_ranges_do_not_use_fabric_semantics(actual,requirement,expected):
    assert matches(actual,requirement) is expected


def test_neoforge_dependency_and_conflict_checks():
    def record(identifier,version,dependencies=None):
        return {'id':identifier,'metadata':{'loader':'NEOFORGE','mods':[{'id':identifier,'version':version}],
            'dependencies':dependencies or [],'client_only_hint':False}}
    config={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.97'}
    dep=lambda identity,requirement,**extra:{'id':identity,'range':requirement,'mandatory':True,**extra}
    root=record('sample','1.0',[dep('minecraft','[26.3]'),dep('neoforge','[26.3.0.22-beta,)'),dep('api','[0.6,1.0)')])
    api=record('api','0.6.6')
    assert mods.dependency_report([root,api],config)['structural_checks']=='passed'
    assert any(x['issue']=='missing_dependency' for x in mods.dependency_report([root],config)['issues'])
    api['metadata']['mods'][0]['version']='1.0'
    assert any(x['issue']=='version_mismatch' for x in mods.dependency_report([root,api],config)['issues'])
    root['metadata']['dependencies']=[dep('api','[1.0,)',mandatory=False,kind='incompatible')]
    assert any(x['issue']=='conflicting_mod' for x in mods.dependency_report([root,api],config)['issues'])
    root['metadata']['dependencies']=[dep('api','[1.0,)',mandatory=False,kind='incompatible',side='CLIENT')]
    assert mods.dependency_report([root,api],config)['structural_checks']=='passed'


def test_create_addition_accepts_the_real_adapted_create_requirement():
    def record(identifier,version,dependencies=()):
        return {'id':identifier,'metadata':{'loader':'NEOFORGE','mods':[{'id':identifier,'version':version}],
            'dependencies':list(dependencies),'client_only_hint':False}}
    requirement={'id':'create','range':'[1.19,2.0),[6.0.11-adapted-1.19,)','mandatory':True}
    records=[record('create','6.0.11-adapted-1.31'),record('createaddition','1.7.0-adapted-0.17',[requirement])]
    config={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.99'}
    result=mods.dependency_report(records,config)
    assert result['structural_checks']=='passed' and result['runtime_compatibility']=='unverified'
    records[0]['metadata']['mods'][0]['version']='6.0.11-adapted-1.18'
    assert mods.dependency_report(records,config)['issues'][0]['issue']=='version_mismatch'


def test_official_catalog_filters_prereleases_and_other_minecraft_versions():
    xml=b'<metadata><groupId>net.neoforged</groupId><artifactId>neoforge</artifactId><versioning><versions><version>26.3.0.97</version><version>26.3.0.100</version><version>26.3.0.101-beta</version><version>26.4.0.1</version><version>21.1.228</version></versions></versioning></metadata>'
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=xml))) as client:
        assert versions.neoforge_versions(client,'26.3')==['26.3.0.100','26.3.0.97']
        assert versions.neoforge_versions(client,'1.21.1')==['21.1.228']


@pytest.mark.parametrize('encoding',['utf-8','utf-16','utf-16-be','utf-16-le'])
def test_catalog_refuses_decoded_dtd_before_expanding_entities(encoding):
    declaration='utf-16' if encoding.startswith('utf-16') else encoding
    xml=('<?xml version="1.0" encoding="'+declaration+'"?>'
         '<!DOCTYPE metadata [<!ENTITY injected "26.3.0.99">]>'
         '<metadata><groupId>net.neoforged</groupId><artifactId>neoforge</artifactId>'
         '<versioning><versions><version>&injected;</version></versions></versioning></metadata>').encode(encoding)
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=xml))) as client:
        with pytest.raises(ValueError,match='version_metadata_limit'):
            versions.neoforge_versions(client,'26.3')


def test_catalog_stops_reading_an_oversized_stream():
    consumed=[]
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for n in range(100):
                consumed.append(n);yield b'x'*65536
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Stream()))) as client:
        with pytest.raises(ValueError,match='version_metadata_limit'):
            versions.neoforge_versions(client,'26.3')
    assert len(consumed)==33


def test_neoforge_archive_identity_and_cached_artifact_integrity(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());store=Store(tmp_path/'state',key)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as jar:
        jar.writestr('META-INF/neoforge.mods.toml','license="LGPL"\n[[mods]]\nmodId="neoforge"\nversion="26.3.0.97"\n')
    raw=stream.getvalue();calls=[]
    def request(req):calls.append(str(req.url));return httpx.Response(200,content=raw)
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        proof=versions.ensure_neoforge_components(store,'26.3.0.97',client)
        assert proof['sha256']==hashlib.sha256(raw).hexdigest()
        assert versions.ensure_neoforge_components(store,'26.3.0.97',client)==proof
        assert len(calls)==1
        path=store.state/'loader-cache/neoforge-26.3.0.97.jar';path.chmod(0o600);path.write_bytes(b'changed')
        repaired=versions.ensure_neoforge_components(store,'26.3.0.97',client)
        assert repaired['sha256']==proof['sha256'] and path.read_bytes()==raw and len(calls)==2
        with pytest.raises(ValueError,match='loader_metadata_identity_invalid'):
            versions.ensure_neoforge_components(store,'26.3.0.98',client)
    selected=versions.runtime_components(store,{'loader':'NEOFORGE','loader_version':'26.3.0.97'})
    assert selected['loader_components']['loader']=='NEOFORGE'
    changed=versions.runtime_components(store,{**selected,'loader_version':'26.3.0.99'})
    assert 'loader_components' not in changed

def test_first_settings_maintenance_acquires_official_neoforge_proof(tmp_path,monkeypatch):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());store=Store(tmp_path/'state',key);calls=[]
    proof={'loader':'NEOFORGE','loader_version':'26.3.0.99','sha256':'a'*64,'components':{'neoforge':'26.3.0.99'}}
    def acquire(st,version):
        assert st is store and version=='26.3.0.99';calls.append(version)
        st.set('loader_components',{'NEOFORGE:'+version:proof});return proof
    monkeypatch.setattr(versions,'ensure_neoforge_components',acquire)
    current={'loader':'NEOFORGE','loader_version':'26.3.0.99','memory_mb':2048}
    assert 'loader_components' not in versions.runtime_components(store,current)
    assert versions.ensure_runtime_components(store,current)['loader_components']==proof and len(calls)==1

def test_version_plan_replaces_only_trusted_system_files(tmp_path,monkeypatch):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());store=Store(tmp_path/'state',key)
    store.set('version_catalog',{'releases':[{'id':'26.3','url':'https://piston-meta.mojang.com/v1/packages/'+'a'*40+'/26.3.json','sha1':'unused'}]})
    metadata={'loader':'NEOFORGE','mods':[{'id':'mcj_guard','version':'1.0.0'}],'dependencies':[
        {'id':'minecraft','range':'[26.3]','mandatory':True}],'client_only_hint':False}
    store.set('guard_catalog',{'artifacts':[{'minecraft':'26.3','loader':'NEOFORGE','sha256':'b'*64,'metadata':metadata}]})
    monkeypatch.setattr(versions,'read_json',lambda *args:{'id':'26.3','type':'release','javaVersion':{'majorVersion':25}})
    monkeypatch.setattr(versions,'neoforge_versions',lambda *args:['26.3.0.97'])
    monkeypatch.setattr(versions,'ensure_neoforge_components',lambda *args:{'loader':'NEOFORGE','loader_version':'26.3.0.97'})
    old={'id':'old_guard','sha256':'c'*64,'source':'system','metadata':{'loader':'FABRIC','mods':[{'id':'mcj_guard','version':'1.0.0'}],'dependencies':[],'client_only_hint':False}}
    proposed={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.97'}
    assert versions.check(store,proposed,[old])['metadata_checks']=='passed'
    user_mod={**old,'source':'upload'}
    blocked=versions.check(store,proposed,[old,user_mod])
    assert blocked['metadata_checks']=='blocked' and any(x['issue']=='loader_mismatch' for x in blocked['issues'])

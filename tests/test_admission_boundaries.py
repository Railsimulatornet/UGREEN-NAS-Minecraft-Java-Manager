"""Admission is checked for the effective TARGET, including packs and restores."""
import hashlib,io,json,os,zipfile
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from mcj import maintenance,mods,packs,player_admission,properties,versions,worlds
from mcj.server_settings import normalize
from mcj.store import Store
from test_security import environment,enroll,post


@pytest.mark.parametrize('separator',['\x0b','\x0c','\x1c','\x1d','\x1e','\x85','\u2028','\u2029'])
def test_non_java_line_separators_cannot_override_admission(separator):
    parsed=properties.loads('white-list=false'+separator+'white-list=true\n')
    assert parsed=={'white-list':'false'+separator+'white-list=true'}
    with pytest.raises(ValueError,match='invalid_server_property'):
        player_admission.require_target(parsed,{'visitor_verified':False,'visitor_client_test':'not_verified_for_this_artifact'})


@pytest.mark.parametrize('separator',['\n','\r','\r\n'])
def test_java_line_separators_keep_last_property_value(separator):
    assert properties.loads('white-list=false'+separator+'white-list=true')['white-list']=='true'


@pytest.mark.parametrize('value',[0,1,'0','1','false ',' false','',None,[],{}])
def test_ambiguous_admission_values_are_rejected(value):
    with pytest.raises(ValueError,match='invalid_server_property'):
        normalize({'version':'26.3'},{'properties':{'white-list':value}})


@pytest.mark.parametrize('value,expected',[(False,'false'),(True,'true'),('FALSE','false'),('TrUe','true')])
def test_valid_boolean_admission_values_are_canonical(value,expected):
    assert normalize({'version':'26.3'},{'properties':{'white-list':value}})['properties']['white-list']==expected


@pytest.mark.parametrize('source_open',[False,True])
@pytest.mark.parametrize('proposed',['false',False,'FALSE'])
def test_version_plan_cannot_carry_open_admission_to_unverified_target(environment,monkeypatch,source_open,proposed):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    current=st.get('server');current['properties']['white-list']='false' if source_open else 'true';st.set('server',current)
    st.set('version_catalog',{'releases':[{'id':'26.3','url':'https://piston-meta.mojang.com/v1/packages/'+'a'*40+'/26.3.json','sha1':'unused'}]})
    guard={'minecraft':'26.3','loader':'NEOFORGE','sha256':'b'*64,'java':25,
           'runtime_test':'passed','tested_loaders':['26.3.0.99'],
           'visitor_verified':False,'visitor_client_test':'not_verified_for_this_artifact'}
    st.set('guard_catalog',{'artifacts':[guard]})
    monkeypatch.setattr(versions,'read_json',lambda *args:{'id':'26.3','type':'release','javaVersion':{'majorVersion':25}})
    monkeypatch.setattr(versions,'neoforge_versions',lambda *args:['26.3.0.99'])
    monkeypatch.setattr(versions,'ensure_neoforge_components',lambda *args:{'loader':'NEOFORGE','loader_version':'26.3.0.99'})
    payload={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.99','properties':{'white-list':proposed}}
    # An old live readiness result cannot prove a different target artifact.
    app.state.rpc=lambda *args:{'ready':True,'visitor_verified':True}
    result=post(client,'/api/versions/plan',payload,csrf)
    assert result.status_code==200 and result.json()['metadata_checks']=='blocked'
    assert {'issue':'visitor_admission_requires_verified_guard'} in result.json()['issues']
    with st.db() as db:
        assert db.execute('SELECT state FROM version_plans').fetchone()[0]=='blocked'
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
    assert st.get('server')==current
    guard.update(visitor_verified=True,visitor_client_test='passed');st.set('guard_catalog',{'artifacts':[guard]})
    assert versions.check(st,payload,[])['metadata_checks']=='passed'
    guard.update(visitor_verified=False,visitor_client_test='not_verified_for_this_artifact');st.set('guard_catalog',{'artifacts':[guard]})
    assert versions.check(st,{**payload,'properties':{'white-list':'true'}},[])['metadata_checks']=='passed'


@pytest.fixture
def candidate_environment(tmp_path,monkeypatch):
    monkeypatch.setenv('MCJ_LAYOUT','legacy')
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());st=Store(tmp_path/'state',key)
    runtime={**st.get('server'),'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.99','java':25,'world':'world'}
    runtime['properties']={'white-list':'true'}
    loader=b'isolated official-loader substitute';loader_sha=hashlib.sha256(loader).hexdigest()
    runtime['loader_components']={'loader':'NEOFORGE','loader_version':'26.3.0.99','sha256':loader_sha}
    scratch=tmp_path/'.restore-tests'/'candidate';data=scratch/'data';data.mkdir(parents=True)
    (scratch/'runtime.json').write_text(json.dumps(runtime))
    (data/'server.properties').write_text('white-list=true\nonline-mode=true\ngamemode=spectator\nforce-gamemode=true\n')
    path=data/'libraries/net/neoforged/neoforge/26.3.0.99/neoforge-26.3.0.99-universal.jar';path.parent.mkdir(parents=True);path.write_bytes(loader)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as jar:jar.writestr('META-INF/neoforge.mods.toml','license="MIT"\n[[mods]]\nmodId="mcj_guard"\nversion="1.0.5"\n')
    raw=stream.getvalue();(tmp_path/'guard.jar').write_bytes(raw)
    guard={'minecraft':'26.3','loader':'NEOFORGE','java':25,'runtime_test':'passed','tested_loaders':['26.3.0.99'],
           'sha256':hashlib.sha256(raw).hexdigest(),'path':'guard.jar','filename':'guard.jar',
           'visitor_verified':False,'visitor_client_test':'not_verified_for_this_artifact'}
    calls=[]
    def isolated(*args,**kwargs):calls.append('isolated');return {'runtime_test':'passed'}
    controller=SimpleNamespace(ROOT=tmp_path,RCON='disposable-rcon-fixture',extract_archive=lambda *args:(scratch,data,{},None),trusted_guard=lambda *args:dict(guard),isolated_data_test=isolated)
    monkeypatch.setattr(maintenance,'store',lambda c:st)
    monkeypatch.setattr(versions,'ensure_runtime_components',lambda st,runtime:runtime)
    monkeypatch.setattr(worlds,'apply_import',lambda *args:None)
    monkeypatch.setattr(mods,'dependency_report',lambda *args:{'structural_checks':'passed','version_range_checks':'passed'})
    if os.name=='nt':
        # Linux can unlink an owner-readable0400 file. Windows maps that mode
        # to the DOS read-only flag; adapt disposable fixture cleanup only.
        original_remove=maintenance.safe_remove
        def remove(c,path):
            assert path.resolve().parent==(tmp_path/'.restore-tests').resolve()
            for entry in path.rglob('*'):
                if entry.is_file() and not entry.is_symlink():entry.chmod(0o600)
            original_remove(c,path)
        monkeypatch.setattr(maintenance,'safe_remove',remove)
    return controller,st,runtime,guard,data,calls


@pytest.mark.parametrize('restore',[False,True])
def test_effective_open_candidate_is_stopped_before_isolation(candidate_environment,restore):
    c,st,runtime,guard,data,calls=candidate_environment
    runtime['properties']['white-list']='false'
    with pytest.raises(ValueError,match='visitor_admission_requires_verified_guard'):
        maintenance.candidate(c,{'path':'fixture'},runtime,'unused',records=[],restore=restore)
    assert calls==[]


def test_selected_pack_properties_cannot_bypass_target_admission(candidate_environment):
    c,st,runtime,guard,data,calls=candidate_environment
    st.set('pack_pending',[{'project_id':'fixture','file_id':'1','name':'Fixture','files':[],'apply_properties':True,'properties':{'white-list':'false'}}])
    with pytest.raises(ValueError,match='visitor_admission_requires_verified_guard'):
        maintenance.candidate(c,{'path':'fixture'},runtime,'unused',records=[])
    assert calls==[] and st.get('pack_pending')


@pytest.mark.parametrize('admission,proved',[('true',False),('false',True)])
def test_closed_target_and_proved_open_target_remain_testable(candidate_environment,admission,proved):
    c,st,runtime,guard,data,calls=candidate_environment
    runtime['properties']['white-list']=admission
    guard.update(visitor_verified=proved,visitor_client_test='passed' if proved else 'not_verified_for_this_artifact')
    built=maintenance.candidate(c,{'path':'fixture'},runtime,'unused',records=[])
    assert calls==['isolated'] and properties.loads((data/'server.properties').read_text())['white-list']==admission
    maintenance.require_candidate_admission(c,built)


@pytest.mark.parametrize('field,value',[
    ('version','1.21.1'),('loader','FABRIC'),('loader_version','26.3.0.100'),('java',21),
])
def test_open_candidate_proof_is_bound_to_exact_runtime(candidate_environment,field,value):
    c,st,runtime,guard,data,calls=candidate_environment
    runtime['properties']['white-list']='false'
    guard.update(visitor_verified=True,visitor_client_test='passed')
    runtime[field]=value
    (data/'server.properties').write_text('white-list=false\n')
    built={'mods':[],'guard':dict(guard),'data':data,'runtime':runtime}
    with pytest.raises(ValueError,match='guard_runtime_combination_not_tested'):
        maintenance.promote(c,built,None,None,None,'restore')
    assert not (c.ROOT/'.rollback').exists()


def test_open_candidate_rejects_malformed_runtime_proof(candidate_environment):
    c,st,runtime,guard,data,calls=candidate_environment
    runtime['properties']['white-list']='false'
    guard.update(visitor_verified=True,visitor_client_test='passed',tested_loaders='26.3.0.99')
    (data/'server.properties').write_text('white-list=false\n')
    with pytest.raises(ValueError,match='guard_runtime_combination_not_tested'):
        maintenance.require_candidate_admission(c,{'guard':dict(guard),'data':data,'runtime':runtime})


def test_closed_candidate_does_not_require_open_visitor_proof(candidate_environment):
    c,st,runtime,guard,data,calls=candidate_environment
    runtime['loader_version']='26.3.0.100'
    (data/'server.properties').write_text('white-list=true\n')
    maintenance.require_candidate_admission(c,{'guard':dict(guard),'data':data,'runtime':runtime})


@pytest.mark.parametrize('effective,reason',[
    ('white\\-list:false\n','visitor_admission_requires_verified_guard'),
    ('white-list=false\x0bwhite-list=true\n','invalid_server_property'),
])
def test_post_isolation_properties_are_checked_again(candidate_environment,effective,reason):
    c,st,runtime,guard,data,calls=candidate_environment
    def modify(*args,**kwargs):
        calls.append('isolated');(data/'server.properties').write_text(effective);return {'runtime_test':'passed'}
    c.isolated_data_test=modify
    with pytest.raises(ValueError,match=reason):
        maintenance.candidate(c,{'path':'fixture'},runtime,'unused',records=[])
    assert calls==['isolated']


@pytest.mark.parametrize('effective',['white-list:false\n','white-list=true\nwhite\\-list=false\n','white-list=fa\\\n  lse\n','white-list=\\u0066alse\n','white-list=0\n','motd=missing whitelist\n','white-list=false\x0bwhite-list=true\n'])
def test_promotion_rechecks_java_effective_file_before_live_side_effects(candidate_environment,effective):
    c,st,runtime,guard,data,calls=candidate_environment
    built={'mods':[],'guard':dict(guard,visitor_verified=True,visitor_client_test='passed'),'data':data,'runtime':runtime}
    (data/'server.properties').write_text(effective)
    # c.target and all deployment methods deliberately do not exist: rejection
    # must happen before promotion even asks for a live container.
    with pytest.raises(ValueError,match='visitor_admission_requires_verified_guard|invalid_server_property'):
        maintenance.promote(c,built,None,None,None,'restore')
    assert not (c.ROOT/'.rollback').exists()


def test_proof_revoked_after_test_and_configuration_drift_are_not_promoted(candidate_environment):
    c,st,runtime,guard,data,calls=candidate_environment
    guard.update(visitor_verified=True,visitor_client_test='passed');runtime['properties']['white-list']='false'
    built=maintenance.candidate(c,{'path':'fixture'},runtime,'unused',records=[])
    guard['visitor_verified']=False
    with pytest.raises(ValueError,match='visitor_admission_requires_verified_guard'):
        maintenance.promote(c,built,None,None,None,'version')
    guard['visitor_verified']=True;built['runtime']['properties']['white-list']='true'
    with pytest.raises(ValueError,match='runtime_configuration_mismatch'):
        maintenance.promote(c,built,None,None,None,'version')
    assert not (c.ROOT/'.rollback').exists()

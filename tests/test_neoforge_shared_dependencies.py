import copy,json,hashlib
import pytest
from mcj.mods import dependency_report,check_modrinth
from mcj import job_control
from test_security import environment,enroll

SERVER={'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.99','java':25}
def meta(identifier,version='1.0',children=(),requirements=()):
    return {'loader':'NEOFORGE','mods':[{'id':identifier,'version':version}],
            'embedded':list(children),'dependencies':list(requirements),'environment':'unknown',
            'client_only_hint':False,'sha256':hashlib.sha256((identifier+version).encode()).hexdigest()}
def record(value):return {'id':value['sha256'],'filename':value['mods'][0]['id']+'.jar','metadata':value}
def required(identifier,version):return {'id':identifier,'range':version,'mandatory':True,'side':'BOTH'}

def test_identical_shared_library_is_one_candidate_without_claiming_runtime_success():
    library=meta('shared_library','1.8.5')
    parents=[record(meta(name,children=[copy.deepcopy(library)],requirements=[required('shared_library','[1.0,)')])) for name in ['mapmod','minimapmod','another_mod']]
    result=dependency_report(parents,SERVER)
    assert result['structural_checks']=='passed' and len(result['nested_resolution'])==2
    assert result['runtime_compatibility']=='unverified' and result['native_loader_is_authoritative']
    assert all(x['identical_nested_sha256']==library['sha256'] for x in result['nested_resolution'])

@pytest.mark.parametrize('change',['bytes','version','metadata','missing_hash'])
def test_ambiguous_or_different_shared_candidates_stay_blocked(change):
    first=meta('shared_library');second=copy.deepcopy(first)
    if change=='bytes':second['sha256']='f'*64
    if change=='version':second['mods'][0]['version']='2.0'
    if change=='metadata':second['dependencies']=[required('absent','[1,)')]
    if change=='missing_hash':second.pop('sha256')
    result=dependency_report([record(meta('first',children=[first])),record(meta('second',children=[second]))],SERVER)
    assert result['structural_checks']=='failed'
    assert any(x['issue']=='duplicate_mod_id' for x in result['issues'])

def test_identical_top_level_mods_are_still_a_conflict():
    library=meta('shared_library')
    assert dependency_report([record(library),record(copy.deepcopy(library))],SERVER)['structural_checks']=='failed'

def test_deduplication_does_not_hide_unsatisfied_parent_requirement():
    library=meta('shared_library','1.8.5')
    result=dependency_report([record(meta('first',children=[library])),record(meta('second',children=[library],requirements=[required('shared_library','[2.0,)')]))],SERVER)
    assert any(x['issue']=='version_mismatch' and x['actual']=='1.8.5' and x['required']=='[2.0,)' for x in result['issues'])

def test_specific_dependency_failure_is_retained_for_the_job(environment):
    app,client,credentials,mail=environment;st=app.state.store
    identifier=app.state.add_job('apply_mods',{'fingerprint':'a'*64},1,'idle_now')
    with st.db() as db:db.execute("UPDATE jobs SET state='running' WHERE id=?",(identifier,))
    report={'issues':[{'id':'a'*64,'issue':'version_mismatch','dependency':'shared_library','actual':'1.0','required':'[2,)'}]}
    with job_control.operation(st,identifier):job_control.dependency_failure(report,[{'id':'a'*64,'filename':'dependent.jar'}])
    with st.db() as db:result=json.loads(db.execute('SELECT result FROM jobs WHERE id=?',(identifier,)).fetchone()[0])
    assert result['dependency_report']['issues'][0]['filename']=='dependent.jar'
    assert result['dependency_report']['issues'][0]['required']=='[2,)'


def test_dashboard_exposes_bounded_dependency_explanation_for_admin(environment):
    app,client,_,_=environment;enroll(environment);st=app.state.store
    issue={'filename':'createaddition.jar','issue':'version_predicate_unverified','dependency':'create',
           'required':'[6.0.11-adapted-1.19,)','actual':'6.0.11-adapted-1.31','unrelated_config':'not-public'}
    identifier=app.state.add_job('apply_mods',{},1,'manual')
    with st.db() as db:
        db.execute("UPDATE jobs SET state='failed',result=? WHERE id=?",(json.dumps({'reason':'dependency_check_failed','dependency_report':{'issues':[issue]*8},'configuration':{'private':'not-public'}}),identifier))
    response=client.get('/api/jobs?summary=true')
    assert response.status_code==200
    result=json.loads(next(row['result'] for row in response.json() if row['id']==identifier))
    assert len(result['dependency_report']['issues'])==5
    assert result['dependency_report']['issues'][0]['actual']=='6.0.11-adapted-1.31'
    assert 'not-public' not in response.text

def test_local_patch_is_never_fingerprinted_against_unmodified_provider(environment,monkeypatch):
    app,client,credentials,mail=environment;st=app.state.store
    value=meta('patched_mod');value['sha512']='d'*128
    with st.db() as db:db.execute("INSERT INTO mods(id,filename,sha256,metadata,source,state,updated,origin) VALUES(?,?,?,?,?,?,?,?)",('a'*64,'patched.jar','a'*64,json.dumps(value),'upload','installed',0,json.dumps({'provider':'manual_patch','url':'https://www.curseforge.com/minecraft/mc-mods/carry-on'})))
    import httpx
    original=httpx.Client
    def reject(request):pytest.fail('A patched artifact must not be resolved by provider hash')
    monkeypatch.setattr('mcj.mods.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(reject),**kwargs))
    check_modrinth(st)
    with st.db() as db:status=json.loads(db.execute('SELECT available FROM mods WHERE id=?',('a'*64,)).fetchone()[0])
    assert status['status']=='locally_patched'

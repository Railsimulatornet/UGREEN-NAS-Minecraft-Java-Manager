import json,time,os,subprocess,sys
import pytest
from mcj import mods
from test_security import environment,enroll,post


def seed(app,count=137):
    st=app.state.store;current=st.get('server');basis=json.dumps(current,sort_keys=True);fingerprint=mods.fingerprint(st)
    with st.db() as db:
        for index in range(count):
            config={**current,'loader':'NEOFORGE','loader_version':'26.3.0.'+str(index%3+97)}
            db.execute('INSERT INTO version_plans(id,created,actor,configuration,report,state,based_on,mod_fingerprint,image_id) VALUES(?,?,?,?,?,?,?,?,?)',(format(index+1,'032x'),1700000000+index//3,1,json.dumps(config),json.dumps({'metadata_checks':'passed'}),'tested' if index%2 else 'metadata_passed',basis,fingerprint,'sha256:'+'1'*64))


def test_all_history_reachable_with_identical_timestamps_and_no_data_mutation(environment):
    app,client,credentials,mail=environment;enroll(environment);seed(app)
    ids=[];cursor=None
    for _ in range(10):
        result=client.get('/api/versions/history',params={'limit':25,**({'cursor':cursor} if cursor else {})})
        assert result.status_code==200;page=result.json();ids.extend(x['id'] for x in page['records']);cursor=page['next_cursor']
        if cursor is None:break
    assert len(ids)==len(set(ids))==137
    with app.state.store.db() as db:assert db.execute('SELECT COUNT(*) FROM version_plans').fetchone()[0]==137


def test_filter_search_and_stale_actions_are_truthful(environment):
    app,client,credentials,mail=environment;enroll(environment);seed(app,12)
    result=client.get('/api/versions/history',params={'q':'NEOFORGE 26.3.0.99','state':'tested'}).json()
    assert len(result['records'])==2
    assert all(x['state']=='tested' and x['configuration']['loader_version']=='26.3.0.99' and x['actionable'] for x in result['records'])
    app.state.store.set('server',{**app.state.store.get('server'),'memory_mb':1024})
    assert all(not x['actionable'] for x in client.get('/api/versions/history').json()['records'])
    assert not client.get('/api/versions/history',params={'q':'%'}).json()['records']
    assert not client.get('/api/versions/history',params={'q':"' OR 1=1 --"}).json()['records']


@pytest.mark.parametrize('params',[{'q':'x'*121},{'state':'invented'},{'limit':0},{'limit':101},{'cursor':'nan:'+'a'*32},{'cursor':'inf:'+'a'*32},{'cursor':'1000:../../escape'},{'cursor':'x'*121}])
def test_invalid_history_queries_are_bounded(environment,params):
    app,client,credentials,mail=environment;enroll(environment)
    assert client.get('/api/versions/history',params=params).status_code==422


def test_history_requires_full_admin_authentication(environment):
    app,client,credentials,mail=environment
    assert client.get('/api/versions/history').status_code==401
    enroll(environment)
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/versions/history').status_code==403


def test_stale_mod_basis_and_missing_test_image_never_offer_apply(environment):
    app,client,credentials,mail=environment;enroll(environment);seed(app,2)
    with app.state.store.db() as db:
        db.execute('UPDATE version_plans SET image_id=NULL WHERE id=?',(format(2,'032x'),))
        db.execute('UPDATE version_plans SET mod_fingerprint=? WHERE id=?',('outdated',format(1,'032x')))
        db.execute("UPDATE version_plans SET state='tested' WHERE id=?",(format(2,'032x'),))
    assert all(not x['actionable'] for x in client.get('/api/versions/history').json()['records'])


def test_cursor_validation_is_present_with_python_optimization():
    script='''from mcj.version_history import history
for cursor in ('nan:'+'a'*32, 'inf:'+'a'*32, '-1:'+'a'*32, '1000:../../escape'):
    try: history(None,cursor=cursor)
    except ValueError as error:
        if str(error) != 'invalid_history_cursor': raise
    else: raise RuntimeError('invalid cursor accepted')
'''
    result=subprocess.run([sys.executable,'-O','-c',script],capture_output=True,text=True,timeout=15,env=dict(os.environ))
    assert result.returncode==0,result.stderr

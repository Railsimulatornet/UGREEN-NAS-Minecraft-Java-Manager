import concurrent.futures
import contextlib
import hashlib
import time
import pytest
from mcj import client_packs
from test_security import environment,enroll,post


def test_admin_delete_delegates_without_holding_cross_process_lock(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];calls=[]
    @contextlib.contextmanager
    def forbidden_lock():
        raise AssertionError('The manager must not hold the shared lock during controller RPC')
        yield
    monkeypatch.setattr(app.state.store,'change_lock',forbidden_lock)
    def rpc(path,payload):
        calls.append((path,payload));return {'count':1,'bytes':123,'confirmation':'a'*64,'active_links':1}
    app.state.rpc=rpc
    result=post(client,'/api/client-packs/delete',{'ids':['1'*32]},csrf)
    assert result.status_code==200 and result.json()['bytes']==123
    assert calls==[('/client-pack/delete',{'ids':['1'*32],'confirmation':None,'actor':1})]
    assert post(client,'/api/client-packs/delete',{'ids':['1'*32]}).status_code==403


def test_controller_delete_rechecks_current_pack_and_atomically_removes_bulk(environment,monkeypatch):
    app,_,_,_=environment;st=app.state.store;folder=st.state/'client-packs';folder.mkdir()
    for n in [1,2,3]:
        raw=('owned-test-pack-'+str(n)).encode();identifier=str(n)*32;(folder/(identifier+'.mrpack')).write_bytes(raw)
        with st.db() as db:db.execute('INSERT INTO client_packs VALUES(?,?,?,?,?,?,?,?)',(identifier,n,time.time(),1,'old' if n<3 else 'current',hashlib.sha256(raw).hexdigest(),len(raw),'{}'))
    with st.db() as db:db.execute('INSERT INTO client_pack_links VALUES(?,?,?,?,?,?,?)',('4'*32,'1'*32,1,time.time(),0,'fixture-hash',None))
    current=['current']
    def observed(root,store):
        def competing_change():
            with store.change_lock():return 'unexpected mutation'
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(RuntimeError,match='maintenance_busy'):pool.submit(competing_change).result()
        return {'fingerprint':current[0]}
    monkeypatch.setattr(client_packs,'snapshot',observed)
    current_preview=client_packs.delete_old(st.state,st,['3'*32],1)
    assert current_preview['current_packs']==1
    preview=client_packs.delete_old(st.state,st,['1'*32,'2'*32],1)
    assert preview['active_links']==1
    current[0]='old'
    with pytest.raises(ValueError,match='selection_changed'):client_packs.delete_old(st.state,st,['1'*32,'2'*32],1,preview['confirmation'])
    assert (folder/('1'*32+'.mrpack')).exists()
    current[0]='current'
    result=client_packs.delete_old(st.state,st,['1'*32,'2'*32],1,preview['confirmation'])
    assert result['deleted'] and (folder/('3'*32+'.mrpack')).exists()
    with st.db() as db:
        assert db.execute('SELECT COUNT(*) FROM client_packs').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM client_pack_links').fetchone()[0]==0
    result=client_packs.delete_old(st.state,st,['3'*32],1,current_preview['confirmation'])
    assert result['deleted'] and not (folder/('3'*32+'.mrpack')).exists()


@pytest.mark.parametrize('reason',['maintenance_busy','delete_item_protected'])
def test_controller_delete_conflicts_are_clear_api_responses(environment,reason):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    def rpc(path,payload):raise RuntimeError(reason)
    app.state.rpc=rpc
    response=post(client,'/api/client-packs/delete',{'ids':['1'*32]},csrf)
    assert response.status_code==409 and response.json()['detail']==reason


def test_restore_test_controller_receives_and_clears_progress_context(environment,monkeypatch):
    # Importing the whole controller requires production Docker/secrets. Execute its
    # unchanged route function with an isolated Store and a test server substitute.
    import ast,json,sys,types
    from pathlib import Path
    from mcj import job_control
    app,_,_,_=environment;st=app.state.store;identifier=app.state.add_job('restore_test',{'id':'a'*32},1)
    with st.db() as db:db.execute("UPDATE jobs SET state='running' WHERE id=?",(identifier,))
    source=Path(__file__).parents[1]/'mcj/controller.py';tree=ast.parse(source.read_text(encoding='utf-8'))
    route=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='restore_test');route.decorator_list=[];route.args.args[0].annotation=None
    module=types.ModuleType('mcj_restore_route_test');monkeypatch.setitem(sys.modules,module.__name__,module)
    def trial(name):job_control.phase('test_starting');job_control.phase('test_running');return {'state':'isolated_server_verified'}
    values={'__name__':module.__name__,'sys':sys,'maintenance':types.SimpleNamespace(store=lambda _:st),'exclusive':contextlib.nullcontext,'isolated_restore_test':trial,'__package__':'mcj'}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[route],type_ignores=[])),str(source),'exec'),values)
    assert values['restore_test'](types.SimpleNamespace(archive='owned-fixture.tar.gz',job_id=identifier))['state']=='isolated_server_verified'
    with st.db() as db:result=json.loads(db.execute('SELECT result FROM jobs WHERE id=?',(identifier,)).fetchone()[0])
    assert [x['stage'] for x in result['phases']]==['preparing','test_starting','test_running']
    job_control.phase('promoting')
    with st.db() as db:assert json.loads(db.execute('SELECT result FROM jobs WHERE id=?',(identifier,)).fetchone()[0])==result


def test_valid_link_count_is_complete_and_excludes_outdated_packs_and_disabled_owners(environment):
    import json
    app,client,_,_=environment;enroll(environment);st=app.state.store
    with st.db() as db:
        for n,fingerprint in [(1,'old'),(2,'current')]:db.execute('INSERT INTO client_packs VALUES(?,?,?,?,?,?,?,?)',(str(n)*32,n,time.time(),1,fingerprint,'fixture',1,json.dumps({'version':'fixture-'+str(n)})))
        for n in range(160):db.execute('INSERT INTO client_pack_links VALUES(?,?,?,?,?,?,?)',(format(n,'032x'),'2'*32,1,time.time(),0,format(n,'064x'),None))
        db.execute('INSERT INTO client_pack_links VALUES(?,?,?,?,?,?,?)',('b'*32,'1'*32,1,time.time(),0,'old-link',None))
        db.execute('INSERT INTO client_pack_links VALUES(?,?,?,?,?,?,?)',('c'*32,'2'*32,2,time.time(),0,'disabled-owner',None))
        db.execute('UPDATE users SET enabled=0 WHERE id=2')
    app.state.rpc=lambda path:{'fingerprint':'current'}
    result=client.get('/api/client-packs');assert result.status_code==200
    data=result.json();counts={x['id']:x['active_links'] for x in data['packs']}
    assert counts=={'1'*32:0,'2'*32:160}
    assert len(data['links'])==100  # The history display limit does not truncate counts.

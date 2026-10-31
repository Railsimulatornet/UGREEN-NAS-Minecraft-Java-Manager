import json
import os
import time
import pytest
from mcj import runtime_storage
from test_security import environment,enroll,post
from test_runtime_independent_rollback import fixture as rollback_fixture


def old_tree(root,version,stamp):
    folder=root/'server/libraries/net/neoforged/neoforge'/version
    folder.mkdir(parents=True)
    path=folder/'loader.jar';path.write_bytes(('loader-'+version).encode())
    os.utime(path,(stamp,stamp));os.utime(folder,(stamp,stamp))
    return folder


def enable(st,days=14):
    st.set('server',{'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.99'})
    st.set('runtime_cleanup',{'enabled':True,'retention_days':days})
    st.set('runtime_cleanup_approval',{'actor':1})


def test_only_old_unused_files_deleted_with_audit_and_current_preserved(environment,tmp_path):
    st=environment[0].state.store;enable(st);now=time.time()
    active=old_tree(tmp_path,'26.3.0.99',now-30*86400)
    stale=old_tree(tmp_path,'26.3.0.97',now-20*86400)
    recent=old_tree(tmp_path,'26.3.0.98',now-86400)
    extra=tmp_path/'server/libraries/shared.jar';extra.write_bytes(b'untouched')
    world=tmp_path/'server/world';world.mkdir();(world/'level.dat').write_bytes(b'world')
    result=runtime_storage.cleanup(st,tmp_path,now)
    assert result['state']=='completed' and result['count']==1 and result['bytes']>0
    assert not stale.exists() and active.exists() and recent.exists() and extra.exists()
    assert (world/'level.dat').read_bytes()==b'world'
    assert st.get('runtime_cleanup_last')==result
    assert runtime_storage.cleanup(st,tmp_path,now)['count']==0
    with st.db() as db:
        row=db.execute("SELECT data FROM events WHERE event='runtime_files_deleted'").fetchone()
        assert json.loads(row[0])['automatic'] is True


@pytest.mark.parametrize('reason',['disabled','revoked','viewer','no_approval','running','planned_version','queued_settings'])
def test_unapproved_or_busy_cleanup_never_deletes(environment,tmp_path,reason):
    st=environment[0].state.store;enable(st);now=time.time();folder=old_tree(tmp_path,'26.3.0.97',now-30*86400)
    if reason=='disabled':st.set('runtime_cleanup',{'enabled':False,'retention_days':14})
    elif reason=='no_approval':st.set('runtime_cleanup_approval',None)
    elif reason in ['revoked','viewer']:
        with st.db() as db:db.execute('UPDATE users SET '+('enabled' if reason=='revoked' else 'admin')+'=0 WHERE id=1')
    else:
        state='running' if reason=='running' else 'planned' if reason=='planned_version' else 'queued'
        kind='version_apply' if reason=='planned_version' else 'server_settings'
        with st.db() as db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',('1'*32,kind,state,now,now,1,'manual','{}',None,1))
    assert runtime_storage.cleanup(st,tmp_path,now)['count']==0
    assert folder.exists()


@pytest.mark.parametrize('independent',[False,True])
def test_required_rollback_preserved_and_verified_independent_copy_retained(environment,tmp_path,independent):
    st=environment[0].state.store;enable(st);live,saved=rollback_fixture(tmp_path,st)
    now=time.time();old=now-30*86400
    for p in [live/'loader.jar',live]:os.utime(p,(old,old))
    if not independent:(saved[0]/'loader.jar').unlink()
    result=runtime_storage.cleanup(st,tmp_path,now)
    assert result['count']==int(independent)
    assert live.exists() is not independent
    assert saved[0].exists()
    if independent:assert (saved[0]/'loader.jar').read_bytes()==b'verified old loader'


def test_shared_hardlink_cannot_be_auto_removed(environment,tmp_path):
    st=environment[0].state.store;enable(st);now=time.time()
    folder=old_tree(tmp_path,'26.3.0.97',now-30*86400)
    os.link(folder/'loader.jar',tmp_path/'shared-copy.jar')
    assert runtime_storage.cleanup(st,tmp_path,now)['count']==0 and folder.exists()


def test_files_changed_after_inventory_are_not_deleted(environment,tmp_path,monkeypatch):
    st=environment[0].state.store;enable(st);now=time.time();folder=old_tree(tmp_path,'26.3.0.97',now-30*86400)
    original=runtime_storage.delete
    def concurrent_change(*args,**kwargs):
        (folder/'loader.jar').write_bytes(b'changed just now')
        return original(*args,**kwargs)
    monkeypatch.setattr(runtime_storage,'delete',concurrent_change)
    with pytest.raises(ValueError,match='too_recent|selection_changed'):runtime_storage.cleanup(st,tmp_path,now)
    assert folder.exists()


@pytest.mark.parametrize('value',[{'enabled':'true'},{'enabled':1},{'retention_days':True},{'retention_days':0},{'retention_days':366},{'path':'/'}])
def test_invalid_policy_rejected(value):
    with pytest.raises(ValueError):runtime_storage.cleanup_policy(value)


def test_policy_route_requires_admin_csrf_and_does_not_delete_immediately(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    assert st.get('runtime_cleanup')['enabled'] is False
    value={'enabled':True,'retention_days':21}
    assert post(client,'/api/versions/local/cleanup-policy',value).status_code==403
    response=post(client,'/api/versions/local/cleanup-policy',value,csrf)
    assert response.status_code==200 and response.json()['policy']==value
    assert st.get('runtime_cleanup_approval')['actor']==1
    assert st.get('runtime_cleanup_last') is None
    assert post(client,'/api/versions/local/cleanup-policy',{'enabled':True,'retention_days':True},csrf).status_code==422
    assert post(client,'/api/versions/local/cleanup-policy',{'enabled':'true','retention_days':14},csrf).status_code==422
    assert post(client,'/api/versions/local/cleanup-policy',{'enabled':False,'retention_days':21},csrf).status_code==200
    assert st.get('runtime_cleanup_approval') is None
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,'/api/versions/local/cleanup-policy',value,csrf).status_code==403


def test_inventory_route_returns_policy_and_last_cleanup(environment):
    app,client,_,_=environment;enroll(environment)
    app.state.rpc=lambda path,payload=None:{'files':[]}
    value=client.get('/api/versions/local').json()
    assert value['cleanup']=={'enabled':False,'retention_days':14} and value['cleanup_last'] is None

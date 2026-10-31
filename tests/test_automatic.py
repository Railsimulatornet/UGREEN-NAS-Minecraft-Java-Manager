import io,json,secrets,time,zipfile
import pytest
from cryptography.fernet import Fernet
from mcj import automatic,mods
from mcj.store import Store


def jar(version):
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:z.writestr('fabric.mod.json',json.dumps({'id':'automatic_test','version':version,'depends':{'minecraft':'26.3'}}))
    return raw.getvalue()


def prepare(tmp_path,enabled=True):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());st=Store(tmp_path/'state',key)
    st.set('maintenance',{**st.get('maintenance'),'automatic':True});st.set('automatic_mod_approval',{'actor':1})
    original=mods.stage(st,tmp_path,jar('1.0'),'old.jar')
    with st.db() as db:db.execute("UPDATE mods SET state='installed',enabled=?,installed_enabled=?,available=? WHERE id=?",
        (int(enabled),int(enabled),json.dumps({'status':'available','version':'1.1'}),original['id']))
    calls=[]
    def enqueue(kind,payload,actor,**kwargs):
        identifier=secrets.token_hex(16);calls.append({'id':identifier,'kind':kind,'payload':payload,'actor':actor,**kwargs})
        with st.db() as db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
            (identifier,kind,'queued',time.time(),time.time(),actor,kwargs['mode'],json.dumps(payload),None,1))
        return identifier
    def rpc(path,payload=None):return {'ready':True,'public_game_bound':False}
    return st,original,calls,enqueue,rpc


@pytest.mark.parametrize('enabled',[False,True])
def test_only_installed_updates_are_staged_and_queue_after_continuous_idle(tmp_path,monkeypatch,enabled):
    st,old,calls,enqueue,rpc=prepare(tmp_path,enabled)
    def stage(store,root,identifier):
        result=mods.stage(store,root,jar('1.1'),'new.jar')
        with store.db() as db:db.execute('UPDATE mods SET replaces=?,enabled=? WHERE id=?',(identifier,int(enabled),result['id']))
        return result
    monkeypatch.setattr(automatic.sources,'stage_update',stage)
    result=automatic.stage_updates(st,tmp_path,rpc,enqueue)
    assert result['state']=='queued' and len(calls)==1 and calls[0]['mode']=='idle_5min' and calls[0]['actor']==1
    assert calls[0]['payload']['automatic'] and calls[0]['approved']
    with st.db() as db:records=[dict(x) for x in db.execute('SELECT * FROM mods')]
    assert next(x for x in records if x['id']==old['id'])['state']=='installed'
    desired=mods.proposed_records(records);assert len(desired)==1 and desired[0]['enabled']==int(enabled)
    assert not (tmp_path/'server').exists()
    assert automatic.stage_updates(st,tmp_path,rpc,enqueue)['state']=='already_queued'
    assert automatic.cancel_queued(st)==1
    with st.db() as db:assert db.execute('SELECT state FROM jobs').fetchone()[0]=='cancelled'


@pytest.mark.parametrize('condition,expected',[
 ('manual','manual_changes_pending'),('disabled','disabled'),('revoked','approval_unavailable'),
 ('unknown_guard','guard_not_ready')])
def test_unapproved_manual_changes_or_unknown_guard_cannot_auto_apply(tmp_path,monkeypatch,condition,expected):
    st,old,calls,enqueue,rpc=prepare(tmp_path)
    def forbidden(*args):raise AssertionError('Provider must not be called')
    monkeypatch.setattr(automatic.sources,'stage_update',forbidden)
    if condition=='manual':
        with st.db() as db:db.execute('UPDATE mods SET enabled=0 WHERE id=?',(old['id'],))
    if condition=='disabled':st.set('maintenance',{**st.get('maintenance'),'automatic':False})
    if condition=='revoked':
        with st.db() as db:db.execute('UPDATE users SET enabled=0 WHERE id=1')
    if condition=='unknown_guard':rpc=lambda *args:{'ready':False,'public_game_bound':True}
    assert automatic.stage_updates(st,tmp_path,rpc,enqueue)['state']==expected and not calls

def test_verified_bound_server_still_requires_guard_and_explicit_automation_approval(tmp_path,monkeypatch):
    st,old,calls,enqueue,rpc=prepare(tmp_path)
    with st.db() as db:db.execute('UPDATE mods SET available=NULL')
    assert automatic.stage_updates(st,tmp_path,lambda *args:{'ready':True,'public_game_bound':True},enqueue)['state']=='up_to_date'
    assert not calls
    st.set('automatic_mod_approval',None)
    assert automatic.stage_updates(st,tmp_path,lambda *args:{'ready':True,'public_game_bound':True},enqueue)['state']=='approval_unavailable'


def test_failed_partial_staging_is_quarantined_without_install_or_auto_approval(tmp_path,monkeypatch):
    st,old,calls,enqueue,rpc=prepare(tmp_path)
    def failed(store,root,identifier):
        mods.stage(store,root,jar('1.1'),'new.jar')
        raise ValueError('candidate_mod_dependencies_failed')
    monkeypatch.setattr(automatic.sources,'stage_update',failed)
    with pytest.raises(ValueError):automatic.stage_updates(st,tmp_path,rpc,enqueue)
    assert not calls and not (tmp_path/'server').exists()
    assert automatic.stage_updates(st,tmp_path,rpc,enqueue)['state']=='manual_changes_pending'

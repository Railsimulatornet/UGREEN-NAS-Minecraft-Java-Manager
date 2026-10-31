import io,json,os,time,zipfile
import pytest
from mcj import automatic,mods
from test_automatic import prepare,jar

def drop(root,identifier='folder_mod',depends=None):
    target=root/'mods';target.mkdir(exist_ok=True)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('fabric.mod.json',json.dumps({'id':identifier,'version':'1.0','depends':depends or {'minecraft':'26.3'}}))
    p=target/(identifier+'.jar');p.write_bytes(stream.getvalue());os.utime(p,(time.time()-5,time.time()-5));return p

def approve(st):
    st.set('maintenance',{**st.get('maintenance'),'folder_automatic':True})
    st.set('folder_mod_approval',{'actor':1,'at':100})

def ready(*args):return {'ready':True,'visitor_verified':True}

def test_new_folder_mod_queues_once_without_taking_manual_upload_or_toggle(tmp_path):
    st,old,calls,enqueue,_=prepare(tmp_path);approve(st)
    manual=mods.stage(st,tmp_path,jar('2.0'),'manual.jar')
    drop(tmp_path);mods.scan_drop_folder(st,tmp_path)
    assert automatic.stage_folder_mods(st,tmp_path,ready,enqueue)['state']=='queued'
    assert len(calls)==1 and calls[0]['mode']=='idle_5min' and calls[0]['payload']['automatic_scope']=='folder'
    selection=calls[0]['payload']['selection'];assert manual['id'] not in selection and old['id'] not in selection
    assert len(selection)==1
    assert automatic.stage_folder_mods(st,tmp_path,ready,enqueue)['state']=='already_queued'
    automatic.cancel_folder_queued(st)
    with st.db() as db:db.execute('UPDATE mods SET enabled=0 WHERE id=?',(old['id'],))
    assert automatic.stage_folder_mods(st,tmp_path,ready,enqueue)['state']=='manual_changes_pending'

@pytest.mark.parametrize('reason',['disabled','unverified','missing_dependency','old_approval','corrupt'])
def test_unapproved_or_unsafe_folder_changes_never_install(tmp_path,reason):
    st,_,calls,enqueue,_=prepare(tmp_path);approve(st)
    p=drop(tmp_path,depends={'missing_mod':'*'} if reason=='missing_dependency' else None)
    if reason=='corrupt':p.write_bytes(b'not a jar');os.utime(p,(time.time()-5,time.time()-5))
    mods.scan_drop_folder(st,tmp_path)
    if reason=='disabled':st.set('maintenance',{**st.get('maintenance'),'folder_automatic':False})
    if reason=='old_approval':st.set('folder_mod_approval',{'actor':1,'at':101})
    rpc=(lambda *args:{'ready':True,'visitor_verified':False}) if reason=='unverified' else ready
    result=automatic.stage_folder_mods(st,tmp_path,rpc,enqueue)
    assert result['state']!='queued' and not calls and not (tmp_path/'server').exists()

def test_partially_copied_file_is_not_staged_and_valid_copy_is_idempotent(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);approve(st);p=drop(tmp_path)
    os.utime(p,None);mods.scan_drop_folder(st,tmp_path)
    assert not (st.get('manual_imports') or {})
    os.utime(p,(time.time()-5,time.time()-5));mods.scan_drop_folder(st,tmp_path);first=st.get('manual_imports')
    mods.scan_drop_folder(st,tmp_path);assert st.get('manual_imports')==first


def test_previously_removed_known_bytes_can_be_reinstalled_by_folder_approval(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);approve(st);path=drop(tmp_path)
    previous=mods.stage(st,tmp_path,path.read_bytes(),path.name,source='upload')
    # This is the persistent state left by the normal completed uninstall.
    with st.db() as db:
        db.execute("UPDATE mods SET state='superseded',enabled=0,installed_enabled=0 WHERE id=?",(previous['id'],))
    mods.scan_drop_folder(st,tmp_path)
    assert automatic.stage_folder_mods(st,tmp_path,ready,enqueue)['state']=='queued'
    assert len(calls)==1 and calls[0]['payload']['selection']==[previous['id']]
    with st.db() as db:row=dict(db.execute('SELECT * FROM mods WHERE id=?',(previous['id'],)).fetchone())
    assert row['state']=='staged' and row['source']=='manual' and row['enabled']==1 and row['installed_enabled']==0
    assert automatic.stage_folder_mods(st,tmp_path,ready,enqueue)['state']=='already_queued'

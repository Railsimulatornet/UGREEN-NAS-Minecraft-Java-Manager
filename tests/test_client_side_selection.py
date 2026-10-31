import copy,json,time,os
import pytest
from mcj import client_packs as cp,storage_admin
from test_client_packs import pack_env,record,ACTIVE
from test_security import environment,enroll,post

def test_selection_is_admin_csrf_protected_and_delegated(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];calls=[]
    app.state.rpc=lambda path,payload:calls.append((path,payload)) or {'saved':True}
    value={'sha256':'a'*64,'basis':'b'*64,'side':'required'}
    assert post(client,'/api/client-packs/side',value).status_code==403
    assert post(client,'/api/client-packs/side',value|{'side':'invented'},csrf).status_code==422
    assert post(client,'/api/client-packs/side',value,csrf).status_code==200
    assert calls==[('/client-pack/side',value|{'actor':1})]
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,'/api/client-packs/side',value,csrf).status_code==403

def test_exact_file_selection_and_guard_exclusion(environment,monkeypatch):
    app,_,_,_=environment;st=app.state.store;entry,_=record('Uncertain','uncertain');guard,_=record('Guard','mcj_guard',source='system')
    records=[entry,guard]
    def snapshot(*_):
        sides=cp.side_choices(st,records)
        return {'mods':records,'client_sides':sides,'fingerprint':cp.fingerprint(ACTIVE,records,client_sides=sides)}
    monkeypatch.setattr(cp,'snapshot',snapshot)
    basis=snapshot()['fingerprint'];sha=entry['hashes']['sha256']
    with pytest.raises(ValueError,match='server_only'):cp.set_side(st.state,st,guard['hashes']['sha256'],'required',basis,1)
    cp.set_side(st.state,st,sha,'optional',basis,1)
    assert snapshot()['fingerprint']!=basis
    with pytest.raises(ValueError,match='source_changed'):cp.set_side(st.state,st,sha,'required',basis,1)
    assert cp.side_choices(st,records)=={sha:'optional'}
    new=copy.deepcopy(entry);new['hashes']=cp.hashes(b'new-version')
    assert cp.side_choices(st,[new])=={}
    app.state.add_job('client_pack_build',{},1)
    with pytest.raises(ValueError,match='busy'):cp.set_side(st.state,st,sha,'auto',snapshot()['fingerprint'],1)

def test_manual_client_choice_requires_exact_public_download(environment,monkeypatch):
    app,_,_,_=environment;st=app.state.store;entry,raw=record('NewMod','newmod')
    entry['origin']={'provider':'curseforge','project_id':999999,'file_id':12345}
    monkeypatch.setattr(cp,'modrinth_record',lambda *_:None)
    class Provider:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def get(self,path):return {'modId':999999,'id':12345,'isAvailable':True,'gameVersions':['26.3','NeoForge'],'fileLength':len(raw),'hashes':[{'algo':1,'value':entry['hashes']['sha1']}],'downloadUrl':'https://edge.forgecdn.net/files/1/fixture.jar'}
    monkeypatch.setattr(cp.sources,'CurseForge',Provider)
    assert cp.classify(st,entry,ACTIVE)['client']=='unknown'
    st.set('client_mod_sides',{entry['hashes']['sha256']:'optional'})
    assert cp.classify(st,entry,ACTIVE)['client']=='optional'
    entry['size']+=1
    with pytest.raises(ValueError,match='provider_mismatch'):cp.classify(st,entry,ACTIVE)
    entry['origin']={}
    assert cp.classify(st,entry,ACTIVE)['reason']=='client_pack_public_source_required'
    st.set('client_mod_sides',{entry['hashes']['sha256']:'unsupported'})
    assert cp.classify(st,entry,ACTIVE)['client']=='unsupported'
    st.set('client_mod_sides',{entry['hashes']['sha256']:'required'})
    monkeypatch.setattr(cp,'modrinth_record',lambda *_:{'client':'unsupported'})
    assert cp.classify(st,entry,ACTIVE)['reason']=='client_pack_provider_side_conflict'

def test_exact_provider_file_environment_tags_enable_new_mods(environment,monkeypatch):
    st=environment[0].state.store;entry,raw=record('NewCamera','newcamera')
    entry['origin']={'provider':'curseforge','project_id':999991,'file_id':55555}
    file={'modId':999991,'id':55555,'isAvailable':True,'gameVersions':['Client','Server','26.3','NeoForge'],
          'fileLength':len(raw),'hashes':[{'algo':1,'value':entry['hashes']['sha1']}],
          'downloadUrl':'https://edge.forgecdn.net/files/5/555/fixture.jar'}
    class Provider:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def get(self,path):assert path=='/mods/999991/files/55555';return file
    monkeypatch.setattr(cp.sources,'CurseForge',Provider)
    monkeypatch.setattr(cp,'modrinth_record',lambda *_:None)
    assert cp.classify(st,entry,ACTIVE)['client']=='required'
    file['gameVersions'].remove('Client')
    assert cp.classify(st,entry,ACTIVE)['client']=='unknown'
    file['gameVersions'].append('Client');file['hashes'][0]['value']='0'*40
    with pytest.raises(ValueError,match='provider_mismatch'):cp.classify(st,entry,ACTIVE)

def test_link_changes_invalidate_delete_confirmation(pack_env):
    app,_,observed,_=pack_env;st=app.state.store;built=cp.build(st,app.state.rpc,1)
    root=st.state/'client-packs';basis=observed['fingerprint']
    # Windows denies unlinking read-only fixtures; Linux exports stay mode 0400.
    if os.name=='nt':(root/(built['id']+'.mrpack')).chmod(0o600)
    preview=storage_admin.delete(st,root,'client_pack',[built['id']],1,current_fingerprint=basis)
    cp.share(st,built['id'],1,7)
    with pytest.raises(ValueError,match='selection_changed'):
        storage_admin.delete(st,root,'client_pack',[built['id']],1,current_fingerprint=basis,confirmation=preview['confirmation'])
    preview=storage_admin.delete(st,root,'client_pack',[built['id']],1,current_fingerprint=basis)
    assert preview['active_links']==1 and preview['versions']==[cp.__version__+'-client.1'] and preview['current_packs']==1
    storage_admin.delete(st,root,'client_pack',[built['id']],1,current_fingerprint=basis,confirmation=preview['confirmation'])
    assert cp.build(st,app.state.rpc,1)['version']==cp.__version__+'-client.2'

import hashlib,json,time
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pytest
from mcj import mod_versions,sources,mods
from test_security import environment,enroll,post

ORIGINAL='a'*64;REPLACEMENT='b'*64
URL='https://www.curseforge.com/minecraft/mc-mods/fixture-mod'

def installed(st,root):
    st.set('server',{**st.get('server'),'loader':'NEOFORGE','loader_version':'26.3.0.99'})
    meta={'mods':[{'id':'fixture_mod','name':'Fixture Mod','version':'2.0'}],'dependencies':[]}
    with st.db() as db:db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,enabled,installed_enabled,origin,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',(ORIGINAL,'active.jar',ORIGINAL,json.dumps(meta),'curseforge','installed',1,1,json.dumps({'provider':'curseforge','url':URL,'project_id':42,'file_id':20}),time.time()))
    path=root/'mods/active.jar';path.parent.mkdir(exist_ok=True);path.write_bytes(b'original-active-file')
    return meta,path

def test_catalog_restricts_stable_matching_minecraft_and_loader(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;installed(st,st.state.parent)
    files=[{'id':20,'modId':42,'releaseType':1,'isAvailable':True,'displayName':'2.0','fileName':'latest.jar','gameVersions':['26.3','NeoForge']},
           {'id':10,'modId':42,'releaseType':1,'isAvailable':True,'displayName':'1.0','fileName':'older.jar','gameVersions':['26.3','NeoForge']},
           {'id':9,'modId':42,'releaseType':1,'isAvailable':True,'displayName':'Wrong loader','fileName':'bad.jar','gameVersions':['26.3','Fabric']},
           {'id':8,'modId':42,'releaseType':2,'isAvailable':True,'displayName':'Beta','fileName':'beta.jar','gameVersions':['26.3','NeoForge']}]
    class Provider:
        def __init__(self,store):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def project(self,source):assert source['url']==URL;return {'id':42}
        def get(self,path,params):assert params['modLoaderType']==6 and params['gameVersion']=='26.3';return files
    monkeypatch.setattr(sources,'CurseForge',Provider)
    data=client.get('/api/mods/'+ORIGINAL+'/versions').json();assert [x['id'] for x in data['versions']]==['20','10']
    assert data['current_id']=='20' and data['current_filename']=='active.jar'
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/mods/'+ORIGINAL+'/versions').status_code==403

def test_selected_version_uses_existing_verified_pipeline_without_touching_active_file(environment,monkeypatch):
    app,_,_,_=environment;st=app.state.store;root=st.state.parent;meta,path=installed(st,root);seen=[]
    def stage(store,target,source):
        seen.append(source)
        with store.db() as db:db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,origin,updated,replaces) VALUES(?,?,?,?,?,?,?,?,?)',(REPLACEMENT,'older.jar',REPLACEMENT,json.dumps(meta),'curseforge','staged',json.dumps({'provider':'curseforge','url':URL,'file_id':10}),time.time(),ORIGINAL))
        return {'staged':[{'id':REPLACEMENT}],'installed':False}
    monkeypatch.setattr(sources,'stage_source',stage)
    basis=mod_versions.basis(st,ORIGINAL);result=mod_versions.stage(st,root,ORIGINAL,'10',basis,True)
    assert seen[0]['file_id']==10 and seen[0]['url']==URL and not result['installed']
    assert path.read_bytes()==b'original-active-file'
    with st.db() as db:
        old=db.execute('SELECT installed_enabled FROM mods WHERE id=?',(ORIGINAL,)).fetchone()[0]
        new=dict(db.execute('SELECT * FROM mods WHERE id=?',(REPLACEMENT,)).fetchone())
    assert old==1 and new['installed_enabled']==0 and json.loads(new['origin'])['pinned'] is True

def test_stale_runtime_bad_version_and_pending_changes_never_download(environment,monkeypatch):
    app,_,_,_=environment;st=app.state.store;root=st.state.parent;installed(st,root)
    monkeypatch.setattr(sources,'stage_source',lambda *args:pytest.fail('Unexpected download'))
    with pytest.raises(ValueError,match='mod_search_runtime_changed'):mod_versions.stage(st,root,ORIGINAL,'10','0'*64)
    with pytest.raises(ValueError,match='invalid_mod_version'):mod_versions.stage(st,root,ORIGINAL,'../bad',mod_versions.basis(st,ORIGINAL))
    with st.db() as db:db.execute('UPDATE mods SET remove_pending=1 WHERE id=?',(ORIGINAL,))
    with pytest.raises(ValueError,match='mod_removal_pending'):mod_versions.catalog(st,ORIGINAL)

def test_version_job_requires_admin_csrf_and_pending_update_can_be_discarded(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;meta,path=installed(st,st.state.parent)
    payload={'kind':'mod_version','mode':'manual','payload':{'id':ORIGINAL,'version':'10','basis':mod_versions.basis(st,ORIGINAL),'pin':True}}
    assert post(client,'/api/jobs',payload).status_code==403
    response=post(client,'/api/jobs',payload,csrf);assert response.status_code==200
    with st.db() as db:
        db.execute("UPDATE jobs SET state='cancelled' WHERE id=?",(response.json()['id'],))
        db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,origin,updated,replaces) VALUES(?,?,?,?,?,?,?,?,?)',(REPLACEMENT,'older.jar',REPLACEMENT,json.dumps(meta),'curseforge','staged','{}',time.time(),ORIGINAL))
    assert client.get('/api/mods/'+ORIGINAL+'/versions').json()['detail']=='mod_update_pending'
    assert post(client,'/api/mods/'+ORIGINAL+'/update/cancel',{},csrf).json()['cancelled']==1
    assert path.read_bytes()==b'original-active-file'
    with st.db() as db:assert db.execute('SELECT state FROM mods WHERE id=?',(ORIGINAL,)).fetchone()[0]=='installed'


def test_pinned_modrinth_version_is_not_replaced_by_automatic_update_check(environment,monkeypatch):
    app,_,_,_=environment;st=app.state.store;installed(st,st.state.parent)
    with st.db() as db:db.execute('UPDATE mods SET source=?,origin=? WHERE id=?',('modrinth',json.dumps({'provider':'modrinth','url':'https://modrinth.com/mod/fixture-mod','pinned':True}),ORIGINAL))
    class Provider:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,*args,**kwargs):pytest.fail('Pinned version was checked for replacement')
    monkeypatch.setattr(mods.httpx,'Client',Provider)
    mods.check_modrinth(st)
    with st.db() as db:assert json.loads(db.execute('SELECT available FROM mods WHERE id=?',(ORIGINAL,)).fetchone()[0])['status']=='pinned'


def test_scheduled_version_choice_keeps_the_selected_time(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;installed(st,st.state.parent)
    planned=(datetime.now(ZoneInfo('Europe/Berlin'))+timedelta(days=2)).replace(hour=12,minute=0).strftime('%Y-%m-%dT%H:%M')
    response=post(client,'/api/jobs',{'kind':'mod_version','mode':'scheduled','schedule_local':planned,'payload':{'id':ORIGINAL,'version':'10','basis':mod_versions.basis(st,ORIGINAL),'pin':False}},csrf)
    assert response.status_code==200,response.text
    with st.db() as db:payload=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(response.json()['id'],)).fetchone()[0])
    assert payload['_scheduled_at']>time.time() and payload['pin'] is False

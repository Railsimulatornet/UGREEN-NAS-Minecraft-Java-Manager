import json
import pytest
from mcj import sources, mods
from test_security import environment, enroll, post


@pytest.fixture
def provider(environment,monkeypatch):
    app,client,credentials,mail=environment;st=app.state.store
    st.set('server',{**st.get('server'),'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.97'})
    calls=[]
    project={'id':123,'gameId':432,'classId':6,'name':'A real mod name','summary':'Description, not HTML','authors':[{'name':'Author'}],
             'links':{'websiteUrl':'https://www.curseforge.com/minecraft/mc-mods/example-mod'}}
    file={'id':456,'modId':123,'fileName':'example-26.3.jar','displayName':'Example 1.2','gameVersions':['26.3','NeoForge'],
          'releaseType':1,'isAvailable':True,'fileLength':12345,'downloadUrl':'https://mediafilez.forgecdn.net/files/example.jar',
          'dependencies':[{'modId':789,'relationType':3}]}
    class Provider:
        def __init__(self,store):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,path,params=None):
            calls.append((path,params))
            if path=='/mods/search':return [project,{**project,'id':999,'gameId':0}]
            if path=='/mods/123':return project
            raise AssertionError(path)
        def file(self,p,source,server):
            calls.append(('file',{'source':source,'server':server}))
            return file
    monkeypatch.setattr(sources,'CurseForge',Provider)
    return app,client,st,calls,project,file


def test_search_filters_minecraft_neoforge_stable_mod_class_and_caches(provider):
    app,client,st,calls,project,file=provider
    result=sources.search_curseforge(st,'example')
    assert result['basis']=={'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.97'}
    assert len(result['results'])==1 and result['results'][0]['file_id']==456
    assert result['results'][0]['required_projects']==[789]
    params=calls[0][1]
    assert params['gameId']==432 and params['classId']==6 and params['modLoaderType']==6 and params['gameVersion']=='26.3'
    assert calls[1][1]['source']['allow_prerelease'] is False
    assert sources.search_curseforge(st,'example')==result and len(calls)==2
    with pytest.raises(ValueError):sources.search_curseforge(st,'x')
    with pytest.raises(ValueError):sources.search_curseforge(st,'example',-1)


def test_search_requires_authenticated_admin_and_install_is_one_deduplicated_job(provider,environment):
    app,client,st,calls,project,file=provider
    assert client.get('/api/mods/curseforge/search?query=example').status_code==401
    csrf=enroll(environment)['csrf'];response=client.get('/api/mods/curseforge/search?query=example');assert response.status_code==200
    body={'kind':'curseforge_install','payload':{'project_id':123,'file_id':456,'basis':response.json()['basis']},'mode':'idle_now'}
    first=post(client,'/api/jobs',body,csrf);second=post(client,'/api/jobs',body,csrf)
    assert first.status_code==200 and first.json()['id']==second.json()['id']
    with st.db() as db:assert db.execute("SELECT COUNT(*) FROM jobs WHERE kind='curseforge_install'").fetchone()[0]==1
    body['payload']['basis']['loader_version']='wrong'
    assert post(client,'/api/jobs',body,csrf).status_code==409
    assert post(client,'/api/jobs',body).status_code==403
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE username=\'Roman\'')
    assert client.get('/api/mods/curseforge/search?query=example').status_code==403


def test_exact_selected_file_and_dependencies_are_staged_without_installing(provider,monkeypatch):
    app,client,st,calls,project,file=provider;captured=[]
    def prepare(store,root,api,roots):
        captured.extend(roots)
        return [{'id':'a'*64,'origin':{'project_id':123,'pinned':True,'file_id':456}}]
    monkeypatch.setattr(sources,'prepare_curseforge',prepare)
    monkeypatch.setattr(sources,'register_prepared',lambda store,prepared:prepared)
    result=sources.stage_curseforge_selection(st,'unused',123,456,{'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.97'})
    assert captured[0][1]['file_id']==456 and captured[0][1]['allow_prerelease'] is False
    assert result[0]['origin']['pinned'] is False
    with pytest.raises(ValueError,match='runtime_changed'):sources.stage_curseforge_selection(st,'unused',123,456,{'version':'old'})


def test_one_selected_mod_install_preserves_other_pending_changes():
    def row(letter,state,replaces=None,enabled=1,installed=0):
        return {'id':letter*64,'state':state,'replaces':replaces*64 if replaces else None,'enabled':enabled,'installed_enabled':installed}
    records=[row('a','installed',enabled=0,installed=1),row('b','staged','a'),row('c','staged','b'),
             row('d','installed',enabled=0,installed=1),row('e','staged','d')]
    selected=mods.selected_records(records,['c'*64]);proposed=mods.proposed_records(selected)
    assert {x['id'] for x in proposed}=={'c'*64,'d'*64}
    assert next(x for x in proposed if x['id']=='d'*64)['enabled']==1
    assert next(x for x in records if x['id']=='e'*64)['state']=='staged'
    with pytest.raises(ValueError):mods.selected_records(records,['f'*64])

import pytest
from mcj import ui_preferences
from test_security import environment,enroll,post


def test_favorites_are_private_to_each_admin_and_never_change_server_settings(environment):
    app,client,credentials,mail=environment;st=app.state.store
    csrf=enroll(environment)['csrf'];before=st.get('server')
    assert post(client,'/api/profile/ui-preferences',{'favorite_properties':['view-distance','motd','view-distance']},csrf).json()=={'favorite_properties':['motd','view-distance']}
    assert st.get('server')==before
    assert post(client,'/api/auth/logout',csrf=csrf).status_code==200
    csrf=enroll(environment,name='Moritz')['csrf']
    assert client.get('/api/profile/ui-preferences').json()=={'favorite_properties':[]}
    assert post(client,'/api/profile/ui-preferences',{'favorite_properties':['simulation-distance']},csrf).status_code==200
    assert ui_preferences.own(st,1)=={'favorite_properties':['motd','view-distance']}
    assert ui_preferences.own(st,2)=={'favorite_properties':['simulation-distance']}


@pytest.mark.parametrize('payload',[{'favorite_properties':['rcon.password']},{'favorite_properties':['management-server-secret']},{'favorite_properties':['../escape']},{'favorite_properties':['a'*81]},{'favorite_properties':['k'+str(i) for i in range(65)]},{'favorite_properties':[],'user_id':2}])
def test_invalid_or_other_user_preferences_rejected(environment,payload):
    csrf=enroll(environment)['csrf'];client=environment[1]
    assert post(client,'/api/profile/ui-preferences',payload,csrf).status_code==422
    assert client.get('/api/profile/ui-preferences').json()=={'favorite_properties':[]}


def test_favorites_require_full_auth_admin_and_csrf(environment):
    app,client,credentials,mail=environment
    assert client.get('/api/profile/ui-preferences').status_code==401
    csrf=enroll(environment)['csrf']
    assert post(client,'/api/profile/ui-preferences',{'favorite_properties':[]}).status_code==403
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/profile/ui-preferences').status_code==403
    assert post(client,'/api/profile/ui-preferences',{'favorite_properties':[]},csrf).status_code==403


def test_favorite_preference_visible_with_complete_safe_properties(environment,tmp_path,monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from mcj.web import create_app
    original,unused,credentials,mail=environment
    secret=tmp_path/'fixture-rpc';secret.write_text('disposable-controller-fixture')
    monkeypatch.setenv('RPC_SECRET',str(secret))
    app=create_app(root=tmp_path/'project',keyfile=tmp_path/'encryption',origin='https://testserver',start_worker=False)
    client=TestClient(app,base_url='https://testserver');csrf=enroll((app,client,credentials,mail))['csrf']
    class Controller:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,path):
            assert path=='/properties'
            return httpx.Response(200,json={'view-distance':'32','online-mode':'true','rcon.password':'hidden'})
    monkeypatch.setattr(httpx,'Client',Controller)
    post(client,'/api/profile/ui-preferences',{'favorite_properties':['view-distance']},csrf)
    value=client.get('/api/server/settings').json()
    assert value['ui_preferences']=={'favorite_properties':['view-distance']}
    assert value['properties']=={'view-distance':'32','online-mode':'true'}
    assert 'online-mode' in value['protected']

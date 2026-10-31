import time
import httpx
import pytest
from mcj import versions
from test_security import environment,enroll,post


def test_neoforge_catalog_uses_official_metadata_filters_and_caches(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    st.set('server',{**st.get('server'),'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.97'})
    calls=[];original=httpx.Client
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200,content=b'<metadata><groupId>net.neoforged</groupId><artifactId>neoforge</artifactId><versioning><versions><version>26.3.0.97</version><version>26.3.0.99</version><version>26.2.0.99</version><version>26.3.0.100-beta</version></versions></versioning></metadata>')
    monkeypatch.setattr(versions.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    before=st.get('server')
    for _ in range(2):
        response=client.get('/api/versions/neoforge?minecraft=26.3')
        assert response.status_code==200
        assert response.json()['versions']==['26.3.0.99','26.3.0.97']
    assert calls==[versions.NEOFORGE+'maven-metadata.xml']
    assert st.get('server')==before
    assert client.get('/api/versions/neoforge?minecraft=99.99').status_code==409
    assert client.get('/api/versions/neoforge?minecraft=../../anything').status_code==409
    with st.db() as db:db.execute('UPDATE users SET admin=0')
    assert client.get('/api/versions/neoforge?minecraft=26.3').status_code==403


def test_unavailable_neoforge_catalog_keeps_current_runtime(environment,monkeypatch):
    app,client,_,_=environment;enroll(environment);before=app.state.store.get('server')
    def unavailable(*args,**kwargs):raise httpx.ConnectError('fixture')
    monkeypatch.setattr(versions,'neoforge_catalog',unavailable)
    response=client.get('/api/versions/neoforge?minecraft='+before['version'])
    assert response.status_code==503 and response.json()['detail']=='loader_catalog_unavailable'
    assert app.state.store.get('server')==before

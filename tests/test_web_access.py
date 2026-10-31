import json,time
import pytest
from starlette.requests import Request
from fastapi.testclient import TestClient
from mcj import web_access,auth
from mcj.web import create_app
from test_security import environment,enroll,post

def request(peer,headers=()):
    return Request({'type':'http','method':'GET','path':'/','headers':[(k.encode(),v.encode()) for k,v in headers],'client':(peer,50000),'server':('testserver',443),'scheme':'https'})

def test_only_exact_approved_proxy_may_supply_one_real_client_address():
    proxies=web_access.configured_proxies('172.21.0.5')
    assert web_access.incoming(request('172.21.0.5',[('x-real-ip','203.0.113.8')]),proxies,())==('203.0.113.8',False)
    assert web_access.incoming(request('172.21.0.5',[('x-real-ip','192.168.120.12')]),proxies,())==('192.168.120.12',True)
    assert web_access.incoming(request('172.21.0.6',[('x-real-ip','127.0.0.1')]),proxies,())==('172.21.0.6',False)
    for headers in [[],[('x-real-ip','127.0.0.1, 203.0.113.8')],[('x-real-ip','127.0.0.1'),('x-real-ip','203.0.113.8')],[('x-real-ip','fe80::1')]]:
        assert web_access.incoming(request('172.21.0.5',headers),proxies,())==(None,False)
    with pytest.raises(ValueError):web_access.configured_proxies('172.21.0.0/16')
    with pytest.raises(ValueError):web_access.configured_local_networks('0.0.0.0/0')

@pytest.mark.parametrize('value',['http://example.test','https://example.test/path','https://name:secret@example.test','https://example.test?x=1','https://example.test#x','https://example.test:65536','https://*.example.test','https://bad..test'])
def test_invalid_address_never_becomes_an_allowed_host(value):
    with pytest.raises(ValueError,match='invalid_web_address'):web_access.address(value)

def test_address_change_is_pending_until_same_admin_signs_in_at_new_address(environment):
    app,client,_,_=environment;enroll(environment);st=app.state.store;actor={'id':1};initial=web_access.settings(st,'https://testserver')
    selected={'address':'https://new.example.test','external_web':True}
    with pytest.raises(ValueError,match='confirmation_required'):web_access.change(st,'https://testserver',actor,selected,initial['basis'],'',True,True)
    pending=web_access.change(st,'https://testserver',actor,selected,initial['basis'],selected['address'],True,True)
    assert pending['address']=='https://testserver' and pending['pending']['address']==selected['address']
    with pytest.raises(ValueError,match='not_verified'):web_access.activate(st,'https://testserver',actor,'https://testserver',pending['basis'])
    with pytest.raises(ValueError,match='other_admin'):web_access.activate(st,'https://testserver',{'id':2},selected['address'],pending['basis'])
    activated=web_access.activate(st,'https://testserver',actor,selected['address'],pending['basis'])
    assert activated['address']==selected['address'] and not activated.get('pending')
    assert web_access.allowed_origins(activated)==[selected['address']]
    assert client.get('/api/auth/me').status_code==400
    fresh=client.get(selected['address']+'/api/auth/me')
    assert fresh.status_code==401 and auth.COOKIE not in fresh.request.headers.get('cookie','')

def test_expired_pending_address_keeps_original_working_and_cannot_be_activated(environment):
    app,_,_,_=environment;st=app.state.store
    st.set('web_access',{'address':'https://testserver','external_web':True,'pending':{'address':'https://new.test','expires':time.time()-1,'actor':1}})
    current=web_access.settings(st,'https://testserver');assert web_access.allowed_origins(current)==['https://testserver']
    with pytest.raises(ValueError,match='not_verified'):web_access.activate(st,'https://testserver',{'id':1},'https://new.test',current['basis'])

def test_external_access_enforced_before_auth_and_forwarded_spoof_does_not_unlock_it(environment,monkeypatch):
    app,old,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    monkeypatch.setenv('MCJ_TRUSTED_PROXIES','172.21.0.5')
    localapp=create_app(state=st.state,keyfile=st.state.parent.parent/'encryption',root=st.state.parent,origin='https://testserver',start_worker=False)
    client=TestClient(localapp,base_url='https://testserver',client=('172.21.0.5',50000));client.cookies.update(old.cookies)
    headers={'x-real-ip':'192.168.120.12','Origin':'https://testserver','X-CSRF-Token':csrf}
    current=client.get('/api/infrastructure/web',headers=headers).json()
    assert current['local_connection'] and current['proxy_configured']
    response=client.post('/api/infrastructure/web',headers=headers,json={'address':'https://testserver','external_web':False,'basis':current['basis']})
    assert response.status_code==200,response.text
    assert client.get('/api/auth/me',headers={'x-real-ip':'203.0.113.8'}).status_code==403
    spoof=TestClient(localapp,base_url='https://testserver',client=('172.21.0.6',50000))
    assert spoof.get('/api/auth/me',headers={'x-real-ip':'127.0.0.1'}).status_code==403
    assert client.get('/api/auth/me',headers=headers).status_code==200
    assert client.post('/api/infrastructure/web',headers={'x-real-ip':'192.168.120.12','Origin':'https://testserver'},json={'address':'https://testserver','external_web':True,'basis':response.json()['basis']}).status_code==403

def test_remote_admin_cannot_disable_the_only_connection(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];current=client.get('/api/infrastructure/web').json()
    response=post(client,'/api/infrastructure/web',{'address':'https://testserver','external_web':False,'basis':current['basis']},csrf)
    assert response.status_code==409 and response.json()['detail']=='web_access_requires_local_connection'

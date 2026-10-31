import time
from test_security import environment,enroll,login,post

def test_connection_rule_change_requires_admin_authenticated_session_csrf_and_local_source(environment,monkeypatch):
    app,client,_,_=environment
    assert client.get('/api/infrastructure/connections').status_code==401
    login(environment);assert client.get('/api/infrastructure/connections').status_code==403
    csrf=enroll(environment)['csrf']
    assert post(client,'/api/infrastructure/connections',{'networks':'192.168.1.0/24','confirmed':True}).status_code==403
    # Fixture host is not a confirmed LAN address. A remembered MFA cookie alone is insufficient.
    response=post(client,'/api/infrastructure/connections',{'networks':'192.168.1.0/24','confirmed':True},csrf)
    assert response.status_code==409 and app.state.store.get('connection_policy') is None

def test_connection_rules_reject_broad_networks_and_preserve_current_connection(environment,monkeypatch):
    from mcj import web_access
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    original=web_access.incoming
    def local(request,proxies,networks):
        # Simulate the socket address, not a forwarded header.
        import ipaddress
        request.scope['client']=('192.168.1.80',12345)
        return original(request,proxies,networks)
    monkeypatch.setattr(web_access,'incoming',local)
    # Establish the same pre-existing network as a native initial installation.
    app.state.store.set('connection_policy',{'proxies':'','networks':'192.168.1.0/24'})
    for values in [{'proxies':'192.168.1.0/24','networks':'192.168.1.0/24'},{'proxies':'','networks':'0.0.0.0/0'},{'proxies':'','networks':'192.168.2.0/24'}]:
        assert post(client,'/api/infrastructure/connections',dict(values,confirmed=True),csrf).status_code==409
    result=post(client,'/api/infrastructure/connections',{'proxies':'192.168.1.30','networks':'192.168.1.0/24','confirmed':True},csrf)
    assert result.status_code==200 and result.json()['minecraft_restart_required'] is False
    assert client.get('/api/infrastructure/connections').json()['proxies']=='192.168.1.30'
    with app.state.store.db() as db:db.execute('UPDATE sessions SET mfa=?',(time.time()-301,))
    assert post(client,'/api/infrastructure/connections',{'networks':'192.168.1.0/24','confirmed':True},csrf).status_code==200

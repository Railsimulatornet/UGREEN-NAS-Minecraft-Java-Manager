import hashlib,json,sys,time
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from mcj import bootstrap

@pytest.fixture
def browser(tmp_path):
    code='Disposable-Long-Setup-Fixture-2026';key=Fernet.generate_key();(tmp_path/'queue.key').write_bytes(key);(tmp_path/'status.json').write_text('{"phase":"ready"}')
    context={'origin':'https://192.168.1.50:8090','address':'192.168.1.50','parents':['/volume1/docker','/volume2/Backups'],'network':'192.168.1.0/24','maximum_memory_mb':8192,'recommended_memory_mb':6144,'created':time.time(),'code_hash':hashlib.sha256(code.encode()).hexdigest()}
    client=TestClient(bootstrap.create_app(tmp_path,context),base_url=context['origin'])
    return client,tmp_path,context,code,key

def unlock(browser):
    client,_,context,code,_=browser
    response=client.post('/setup/unlock',json={'code':code},headers={'Origin':context['origin']});assert response.status_code==200
    return {'Origin':context['origin'],'X-CSRF':response.json()['csrf']}

def payload():return {'parent':0,'backup_parent':1,'folder':'minecraft','backup_folder':'worlds','username':'Owner','email':'owner@example.test','password':'Fixture-Secret-2026!','access_mode':'internal','memory_mb':6144,'accept_eula':True}

def test_installer_no_first_user_claim_without_nas_code(browser):
    client,base,context,code,key=browser
    assert client.get('/').status_code==200
    assert client.get('/setup/state').status_code==401
    assert client.post('/setup/install',json=payload(),headers={'Origin':context['origin']}).status_code==401
    assert client.post('/setup/unlock',json={'code':code}).status_code==403
    assert client.get('/',headers={'Host':'evil.example.test'}).status_code==421
    headers=unlock(browser);state=client.get('/setup/state');assert state.status_code==200 and state.json()['parents']==context['parents']
    assert 'code_hash' not in state.text and code not in state.text
    assert client.post('/setup/install',json=payload(),headers={'Origin':context['origin']}).status_code==401
    accepted=client.post('/setup/install',json=payload(),headers=headers);assert accepted.status_code==200
    raw=(base/'request.fernet').read_bytes();assert b'Fixture-Secret' not in raw and json.loads(Fernet(key).decrypt(raw))==payload()
    assert client.post('/setup/install',json=payload(),headers=headers).status_code==409

def test_installer_validation_and_reports_never_echo_password(browser):
    client,base,context,_,_=browser;headers=unlock(browser)
    for change in [{'folder':'../etc'},{'folder':'/etc'},{'parent':8},{'memory_mb':16384},{'memory_mb':6145},{'accept_eula':False},{'image':'other:latest'},{'email':'invalid'}]:
        response=client.post('/setup/install',json=payload()|change,headers=headers)
        assert response.status_code==400 and 'Fixture-Secret' not in response.text
        assert not (base/'request.fernet').exists()
    assert client.get('/setup/report').json()['phase']=='ready'
    response=client.post('/setup/unlock',content=b'x'*2049,headers={'Origin':context['origin']});assert response.status_code==413

def test_installer_rate_limit_and_cookie_security(browser):
    client,_,context,code,_=browser
    response=client.post('/setup/unlock',json={'code':code},headers={'Origin':context['origin']})
    cookie=response.headers['set-cookie'];assert '__Host-mcj-setup=' in cookie and 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/' in cookie
    for _ in range(7):assert client.post('/setup/unlock',json={'code':'wrong'},headers={'Origin':context['origin']}).status_code==401
    assert client.post('/setup/unlock',json={'code':code},headers={'Origin':context['origin']}).status_code==429

def test_worker_configuration_never_accepts_arbitrary_paths_commands_or_images(browser):
    _,_,context,_,_=browser
    config,password=bootstrap.selection_config(payload(),context)
    assert config['root']=='/volume1/docker/minecraft' and config['backup_root']=='/volume2/Backups/worlds'
    assert config['public_game'] is False and config['tls_mode']=='selfsigned' and config['trusted_proxies']==''
    assert config['container_memory_mb']==6144
    for change in [{'folder':'x;id'},{'password':'short'},{'parent':-1},{'command':'id'},{'memory_mb':'8192'}]:
        with pytest.raises(ValueError):bootstrap.selection_config(payload()|change,context)


def test_expired_setup_has_a_readable_uncached_page_but_cannot_unlock_or_install(browser):
    _,base,context,code,_=browser
    clock=lambda:context['created']+14401
    client=TestClient(bootstrap.create_app(base,context,clock),base_url=context['origin'])
    page=client.get('/')
    assert page.status_code==410 and 'text/html' in page.headers['content-type']
    assert 'Einrichtungszugang abgelaufen' in page.text and 'Docker → Projekt' in page.text
    assert page.headers['cache-control']=='no-store'
    assert client.get('/bootstrap.css').status_code==200
    assert client.get('/bootstrap-i18n.js').status_code==200
    assert client.get('/static/style.css').status_code==200
    assert client.get('/static/reference-v12.css').status_code==200
    assert client.get('/static/assets/final/ui/frame_wide_hd.png').status_code==200
    for name in ['panel_border_9slice.png','grass_corner_top_left.png','grass_corner_top_right.png']:
        assert client.get('/static/assets/final/ui/'+name).status_code==200
    assert client.get('/static/app.js').status_code==404
    assert client.get('/static/%2e%2e%2fqueue.key').status_code==404
    assert client.get('/setup-assets/frame.png').status_code==200
    assert client.get('/setup-assets/not-allowed.txt').status_code==404
    assert client.get('/setup-assets/%2e%2e%2fqueue.key').status_code==404
    for endpoint,body in [('/setup/unlock',{'code':code}),('/setup/install',payload())]:
        response=client.post(endpoint,json=body,headers={'Origin':context['origin']})
        assert response.status_code==410 and response.headers['cache-control']=='no-store'
    assert not (base/'request.fernet').exists()
    wrong=client.get('/',headers={'Host':'foreign.example.test'})
    assert wrong.status_code==421 and wrong.headers['cache-control']=='no-store'

@pytest.mark.parametrize('address',['0.0.0.0','127.0.0.1','100.64.0.1','169.254.1.1','8.8.8.8','::1'])
def test_initial_listener_requires_a_real_private_ipv4(address):
    with pytest.raises(ValueError):bootstrap.private_ip(address)

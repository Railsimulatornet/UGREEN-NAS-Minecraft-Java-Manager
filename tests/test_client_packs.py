import base64
import copy
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from mcj import client_packs as cp
from mcj.web import create_app
from test_security import environment,enroll,post

ACTIVE={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.97'}

@pytest.mark.parametrize('trusted',[True,False])
def test_public_pack_quota_uses_only_validated_client_identity(pack_env,monkeypatch,trusted):
    app,_,_,_=pack_env;st=app.state.store
    built=cp.build(st,app.state.rpc,1);link=cp.share(st,built['id'],1,7)
    monkeypatch.setenv('MCJ_TRUSTED_PROXIES','172.21.0.5')
    proxyapp=create_app(root=st.state.parent,keyfile=st.state.parent.parent/'encryption',origin='https://testserver',start_worker=False)
    proxyapp.state.rpc=app.state.rpc
    client=TestClient(proxyapp,base_url='https://testserver',client=('172.21.0.5' if trusted else '172.21.0.6',50000))
    headers={'Origin':'https://testserver','X-Real-IP':'203.0.113.8'}
    for attempt in range(60):
        if attempt%2:response=client.post('/client-pack/download',data={'token':'a'*43},headers=headers)
        else:response=client.post('/client-pack/info',json={'token':'a'*43},headers=headers)
        assert response.status_code==404
    assert client.post('/client-pack/info',json={'token':link['token']},headers=headers).status_code==429
    headers['X-Real-IP']='203.0.113.9'
    expected=200 if trusted else 429
    assert client.post('/client-pack/info',json={'token':link['token']},headers=headers).status_code==expected
    assert client.post('/client-pack/download',data={'token':link['token']},headers=headers).status_code==expected
    if trusted:
        for invalid in ['203.0.113.8, 203.0.113.9','not-an-address']:
            headers['X-Real-IP']=invalid
            assert client.post('/client-pack/info',json={'token':link['token']},headers=headers).status_code==403
    client.close()

def record(name,ident,dependencies=(),source='curseforge'):
    raw=('fixture-'+name).encode()
    return {'filename':name+'.jar','hashes':cp.hashes(raw),'size':len(raw),'source':source,'origin':{},
            'metadata':{'loader':'NEOFORGE','environment':'unknown','mods':[{'id':ident,'name':name,'version':'1.0'}],
                        'dependencies':list(dependencies),'embedded':[]}},raw

@pytest.fixture
def pack_env(environment,monkeypatch):
    app,client,creds,mail=environment;st=app.state.store;st.set('server',{**ACTIVE,'properties':{'rcon.password':'MUST-NOT-EXPORT'},'world':'private-world'})
    main,raw=record('ClientRequired','client_mod');guard,_=record('VisitorGuard','mcj_guard',source='system');unknown,_=record('Uncertain','uncertain')
    observed={'runtime':ACTIVE,'mods':[main,guard,unknown]};observed['fingerprint']=cp.fingerprint(ACTIVE,observed['mods'])
    original_classify=cp.classify
    def classify(st,r,a):
        if r['filename']==main['filename']:return {'client':'required','url':'https://cdn.modrinth.com/data/fixture.jar','license':'MIT','evidence':'https://modrinth.com/mod/fixture'}
        if r['filename']==unknown['filename']:return {'client':'unknown','reason':'client_requirements_unknown'}
        return original_classify(st,r,a)
    monkeypatch.setattr(cp,'classify',classify)
    calls=[]
    def rpc(path,payload=None):
        calls.append((path,payload))
        assert path=='/client-pack/snapshot'
        return copy.deepcopy(observed)
    app.state.rpc=rpc
    return app,client,observed,calls

def test_export_exact_runtime_guard_exclusion_unknown_omission_and_no_internal_settings(pack_env):
    app,client,observed,calls=pack_env;result=cp.build(app.state.store,app.state.rpc,1)
    path,row=cp.archive(app.state.store,result['id'])
    with zipfile.ZipFile(path) as archive:
        index=json.loads(archive.read('modrinth.index.json'))
        assert index['dependencies']=={'minecraft':'26.3','neoforge':'26.3.0.97'}
        assert [x['path'] for x in index['files']]==['mods/ClientRequired.jar']
        assert index['files'][0]['hashes']==observed['mods'][0]['hashes']
        assert not any('guard' in x.lower() for x in archive.namelist())
        text=b'\n'.join(archive.read(x) for x in archive.namelist())
        assert b'MUST-NOT-EXPORT' not in text and b'private-world' not in text and b'rcon.password' not in text
        assert b'Uncertain' not in json.dumps(index).encode()
    assert result['excluded']==2
    same=cp.build(app.state.store,app.state.rpc,1)
    assert same['id']==result['id'] and same['already_current']

def test_source_change_blocks_commit(pack_env):
    app,client,observed,calls=pack_env
    def rpc(path,payload=None):
        value=copy.deepcopy(observed);calls.append(path)
        if len(calls)>1:value['fingerprint']='a'*64
        return value
    with pytest.raises(ValueError,match='source_changed'):cp.build(app.state.store,rpc,1)
    assert cp.listing(app.state.store)['packs']==[]


@pytest.mark.parametrize('minecraft,java',[('1.20.1',17),('1.21.1',21),('26.3',25)])
@pytest.mark.parametrize('loader,dependency',[('FABRIC','fabric-loader'),('FORGE','forge'),('NEOFORGE','neoforge')])
def test_export_uses_the_launchers_modrinth_loader_identifier(pack_env,minecraft,java,loader,dependency):
    app,_,observed,_=pack_env;st=app.state.store
    versions={'FABRIC':{'1.20.1':'0.20.1','1.21.1':'0.20.1','26.3':'0.20.1'},
              'FORGE':{'1.20.1':'47.4.28','1.21.1':'52.1.20','26.3':'66.1.0'},
              'NEOFORGE':{'1.20.1':'47.1.106','1.21.1':'21.1.265','26.3':'26.3.0.99'}}
    active={'version':minecraft,'java':java,'loader':loader,'loader_version':versions[loader][minecraft]}
    st.set('server',{**st.get('server'),**active})
    observed['runtime']=active
    observed['mods'][0]['metadata']['loader']='FORGE' if loader=='NEOFORGE' and minecraft=='1.20.1' else loader
    observed['fingerprint']=cp.fingerprint(active,observed['mods'])
    built=cp.build(st,app.state.rpc,1);path,_=cp.archive(st,built['id'])
    with zipfile.ZipFile(path) as archive:
        index=json.loads(archive.read('modrinth.index.json'))
    assert index['dependencies']=={'minecraft':minecraft,dependency:active['loader_version']}
    assert index['files'][0]['hashes']==observed['mods'][0]['hashes']


def test_corrected_fabric_format_rebuilds_without_replacing_a_previous_pack(pack_env):
    app,_,observed,_=pack_env;st=app.state.store
    active={'version':'26.3','java':25,'loader':'FABRIC','loader_version':'0.20.1'}
    st.set('server',{**st.get('server'),**active});observed['runtime']=active
    observed['mods'][0]['metadata']['loader']='FABRIC'
    legacy={'runtime':active,'mods':sorted((x['filename'],x['hashes']['sha256']) for x in observed['mods']),
            'export_policy':cp.EXPORT_POLICY,'exporter_version':cp.__version__}
    legacy_fingerprint=hashlib.sha256(json.dumps(legacy,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    observed['fingerprint']=legacy_fingerprint
    first=cp.build(st,app.state.rpc,1);old_path,_=cp.archive(st,first['id']);old_bytes=old_path.read_bytes()
    observed['fingerprint']=cp.fingerprint(active,observed['mods'])
    assert observed['fingerprint']!=legacy_fingerprint
    second=cp.build(st,app.state.rpc,1)
    assert second['id']!=first['id'] and old_path.read_bytes()==old_bytes
    assert cp.build(st,app.state.rpc,1)['id']==second['id']

def test_client_side_dependency_is_checked_but_server_dependency_is_not():
    base,_=record('base','base',[{'id':'server_helper','side':'SERVER','mandatory':True,'range':'[1,)'},{'id':'client_helper','side':'CLIENT','mandatory':True,'range':'[2,3)'}])
    assert cp.dependency_check([base],ACTIVE)==[{'mod':'base','dependency':'client_helper','reason':'client_dependency_unverified'}]
    helper,_=record('helper','client_helper');helper['metadata']['mods'][0]['version']='2.4'
    base['metadata']['embedded']=[helper['metadata']]
    assert cp.dependency_check([base],ACTIVE)==[]
    helper['metadata']['mods'][0]['version']='3.1'
    assert cp.dependency_check([base],ACTIVE)

def test_dependencies_block_package_not_just_warning(pack_env):
    app,client,observed,calls=pack_env
    observed['mods'][0]['metadata']['dependencies']=[{'id':'missing_client_library','mandatory':True,'side':'CLIENT','range':'[1,)'}]
    with pytest.raises(ValueError,match='dependencies_blocked'):cp.build(app.state.store,app.state.rpc,1)
    assert cp.listing(app.state.store)['packs']==[]
    assert app.state.store.get('client_pack_analysis')['issues'][0]['dependency']=='missing_client_library'

def test_update_versions_and_changelog(pack_env):
    app,client,observed,calls=pack_env;first=cp.build(app.state.store,app.state.rpc,1)
    observed['mods'][0]['hashes']=cp.hashes(b'new fixture');observed['mods'][0]['size']=11
    observed['fingerprint']=cp.fingerprint(ACTIVE,observed['mods'])
    second=cp.build(app.state.store,app.state.rpc,1)
    assert first['id']!=second['id'] and second['version']==cp.__version__+'-client.2'
    assert cp.listing(app.state.store)['packs'][0]['manifest']['changes']['changed']==['ClientRequired.jar']

def test_download_integrity_and_unsafe_paths(pack_env):
    app,client,observed,calls=pack_env;built=cp.build(app.state.store,app.state.rpc,1);path,row=cp.archive(app.state.store,built['id'])
    with pytest.raises(ValueError):cp.archive(app.state.store,'../manager.sqlite3')
    path.chmod(0o600);path.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity_failed'):cp.archive(app.state.store,built['id'])

def test_capability_hashed_expiring_revocable_and_actor_bound(pack_env):
    app,client,observed,calls=pack_env;st=app.state.store;built=cp.build(st,app.state.rpc,1);link=cp.share(st,built['id'],1,7)
    assert cp.authorize_share(st,link['token'],observed['fingerprint'])['pack_id']==built['id']
    with st.db() as db:
        assert link['token'] not in db.execute('SELECT token_hash FROM client_pack_links').fetchone()[0]
        assert link['token'] not in json.dumps([dict(x) for x in db.execute('SELECT * FROM events')])
        db.execute('UPDATE users SET enabled=0 WHERE id=1')
    with pytest.raises(ValueError,match='link_invalid'):cp.authorize_share(st,link['token'],observed['fingerprint'])
    with st.db() as db:db.execute('UPDATE users SET enabled=1 WHERE id=1');db.execute('UPDATE client_pack_links SET expires=?',(time.time()-1,))
    with pytest.raises(ValueError,match='link_invalid'):cp.authorize_share(st,link['token'],observed['fingerprint'])

def test_public_landing_assets_and_token_download_without_account(pack_env):
    app,client,observed,calls=pack_env;st=app.state.store;built=cp.build(st,app.state.rpc,1);link=cp.share(st,built['id'],1,7)
    for path in ['/client-pack','/client-pack/app.js','/client-pack/style.css','/client-pack/icon.svg']:
        response=client.get(path);assert response.status_code==200
        assert response.headers['referrer-policy']=='no-referrer' and response.headers['cache-control']=='no-store'
    assert client.get('/client-pack/manager.sqlite3').status_code==404
    assert client.get('/api/client-packs').status_code==401
    assert client.get('/api/client-packs/'+built['id']+'/download').status_code==401
    response=post(client,'/client-pack/info',{'token':link['token']})
    assert response.status_code==200 and len(response.json()['mods'])==1
    assert response.json()['excluded_unknown']==1 and response.json()['runtime']==ACTIVE
    response=client.post('/client-pack/download',data={'token':link['token']},headers={'Origin':'https://testserver'})
    assert response.status_code==200 and response.content==cp.archive(st,built['id'])[0].read_bytes()
    assert response.headers['content-type']=='application/x-modrinth-modpack+zip'
    assert not client.cookies

def test_invalid_tokens_do_not_invoke_controller_and_origin_csrf_not_bypassed(pack_env):
    app,client,observed,calls=pack_env
    assert post(client,'/client-pack/info',{'token':'a'*43}).status_code==404
    assert calls==[]
    assert post(client,'/client-pack/info',{'token':'a'*43},origin='https://evil.test').status_code==403
    assert client.post('/client-pack/info',json={'token':'a'*43}).status_code==403
    assert post(client,'/api/client-packs/build',{}).status_code==403
    assert client.get('/client-pack/download?token='+'a'*43).status_code==404

def test_revoked_and_stale_downloads_fail_closed(pack_env):
    app,client,observed,calls=pack_env;st=app.state.store;built=cp.build(st,app.state.rpc,1);link=cp.share(st,built['id'],1,7)
    observed['fingerprint']='b'*64
    assert post(client,'/client-pack/info',{'token':link['token']}).status_code==409
    observed['fingerprint']=cp.listing(st)['packs'][0]['fingerprint']
    with st.db() as db:db.execute('UPDATE client_pack_links SET revoked=?',(time.time(),))
    assert post(client,'/client-pack/info',{'token':link['token']}).status_code==404

def test_admin_mfa_csrf_create_and_revoke(pack_env,environment):
    app,client,observed,calls=pack_env;st=app.state.store;result=enroll(environment);csrf=result['csrf']
    assert post(client,'/api/client-packs/build',{},csrf).status_code==200
    built=cp.build(st,app.state.rpc,1)
    response=post(client,'/api/client-packs/'+built['id']+'/share',{'days':7},csrf)
    assert response.status_code==200
    link=response.json();assert link['url'].startswith('https://testserver/client-pack#') and '?' not in link['url']
    assert post(client,'/api/client-packs/'+built['id']+'/share',{'days':31},csrf).status_code==422
    assert post(client,'/api/client-packs/links/'+link['id']+'/revoke',{},csrf).status_code==200
    with st.db() as db:assert db.execute('SELECT revoked FROM client_pack_links').fetchone()[0]

@pytest.mark.parametrize('url',['http://cdn.modrinth.com/file.jar','https://cdn.modrinth.com.evil.test/a','https://user:secret@cdn.modrinth.com/a','https://cdn.modrinth.com/a?key=secret','https://127.0.0.1/a','https://cdn.modrinth.com:443/a'])
def test_external_resources_are_public_provider_only(url):
    with pytest.raises(ValueError):cp.public_url(url)

def test_server_guard_always_excluded_before_provider_lookup(environment,monkeypatch):
    app,_,_,_=environment;r,_=record('Guard','mcj_guard')
    monkeypatch.setattr(cp,'modrinth_record',lambda *args:pytest.fail('Guard provider lookup'))
    assert cp.classify(app.state.store,r,ACTIVE)['client']=='unsupported'

@pytest.mark.parametrize('changes',[{'version':None},{'java':25.0},{'loader_version':None},{'loader':'unknown'}])
def test_runtime_never_guessed(changes):
    with pytest.raises(ValueError):cp.runtime({**ACTIVE,**changes})


@pytest.mark.parametrize('days',[1,7,14,30,None])
def test_share_without_additional_mfa_and_expiry_choices(pack_env,environment,days):
    app,client,observed,calls=pack_env;st=app.state.store;csrf=enroll(environment)['csrf']
    built=cp.build(st,app.state.rpc,1)
    with st.db() as db:db.execute('UPDATE sessions SET mfa=?',(time.time()-900,))
    # Fully authenticated sessions retain MFA assurance beyond the old five-minute window.
    response=post(client,'/api/client-packs/'+built['id']+'/share',{'days':days},csrf)
    assert response.status_code==200
    value=response.json();token=value['url'].split('#',1)[1]
    assert value['expires'] is None if days is None else value['expires']>time.time()
    links=client.get('/api/client-packs').json()['links']
    assert links[0]['version']==cp.listing(st)['packs'][0]['manifest']['version'] and links[0]['expires']==value['expires']
    assert 'token' not in links[0] and 'token_hash' not in links[0]
    anonymous=type(client)(app,base_url='https://testserver')
    response=post(anonymous,'/client-pack/info',{'token':token})
    assert response.status_code==200 and not anonymous.cookies
    downloaded=anonymous.post('/client-pack/download',data={'token':token},headers={'Origin':'https://testserver'})
    assert downloaded.status_code==200
    assert downloaded.content==cp.archive(st,built['id'])[0].read_bytes()
    # Building a package uses the same fully authenticated admin session.
    assert post(client,'/api/client-packs/build',{},csrf).status_code==200
    assert post(client,'/api/client-packs/links/'+value['id']+'/revoke',{},csrf).status_code==200
    assert post(anonymous,'/client-pack/info',{'token':token}).status_code==404
    with st.db() as db:
        events=' '.join(x['data'] for x in db.execute('SELECT data FROM events'))
    assert token not in events and value['url'] not in events


def test_unlimited_explicit_default_and_real_expiry(pack_env,environment,monkeypatch):
    app,client,observed,calls=pack_env;st=app.state.store;csrf=enroll(environment)['csrf'];built=cp.build(st,app.state.rpc,1)
    before=time.time()
    default=post(client,'/api/client-packs/'+built['id']+'/share',{},csrf).json()
    assert before+7*86400<=default['expires']<=time.time()+7*86400
    forever=cp.share(st,built['id'],1,None)
    finite=cp.share(st,built['id'],1,1)
    now=time.time()
    with monkeypatch.context() as m:
        m.setattr(cp.time,'time',lambda:now+366*86400)
        assert cp.authorize_share(st,forever['token'],None)['pack_id']==built['id']
        with pytest.raises(ValueError,match='client_pack_link_invalid'):cp.authorize_share(st,finite['token'],None)
    with st.db() as db:db.execute('UPDATE client_pack_links SET expires=? WHERE id=?',(time.time()-1,finite['id']))
    anonymous=type(client)(app,base_url='https://testserver')
    assert post(anonymous,'/client-pack/info',{'token':finite['token']}).status_code==404
    assert anonymous.post('/client-pack/download',data={'token':finite['token']},headers={'Origin':'https://testserver'}).status_code==404


def test_share_still_requires_verified_admin_csrf_and_valid_session(pack_env,environment):
    app,client,observed,calls=pack_env;st=app.state.store;built=cp.build(st,app.state.rpc,1)
    csrf=enroll(environment)['csrf'];path='/api/client-packs/'+built['id']+'/share'
    assert post(client,path,{'days':None},origin='https://evil.test').status_code==403
    assert post(client,path,{'days':None}).status_code==403
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,path,{'days':None},csrf).json()['detail']=='admin_required'
    with st.db() as db:db.execute('UPDATE users SET admin=1,force_password=1 WHERE id=1')
    assert post(client,path,{'days':None},csrf).json()['detail']=='setup_or_mfa_required'
    with st.db() as db:
        db.execute('UPDATE users SET force_password=0 WHERE id=1')
        db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
    assert post(client,path,{'days':None},csrf).status_code==401


@pytest.mark.parametrize('days',[0,31,-1,True,7.0,'unlimited'])
def test_invalid_share_expiry_not_silently_unlimited(pack_env,environment,days):
    app,client,_,_=pack_env;csrf=enroll(environment)['csrf'];built=cp.build(app.state.store,app.state.rpc,1)
    assert post(client,'/api/client-packs/'+built['id']+'/share',{'days':days},csrf).status_code==422

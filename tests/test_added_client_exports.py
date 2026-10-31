import json,copy
import pytest
from mcj import client_packs as cp
from test_client_packs import pack_env,record,ACTIVE
from test_security import environment

@pytest.mark.parametrize('project,identifier,license_name',[(1683430,'createaddition','MIT'),(1680731,'immersive_aircraft','GPL-3.0-only'),(422301,'sophisticatedbackpacks','All Rights Reserved; official download only'),(618298,'sophisticatedcore','All Rights Reserved; official download only')])
def test_reviewed_client_and_server_mod_uses_exact_verified_provider_file(monkeypatch,project,identifier,license_name):
    entry,raw=record(identifier,identifier);entry['origin']={'provider':'curseforge','project_id':project,'file_id':1234567}
    class Provider:
        def __init__(self,store):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,path):return {'modId':project,'id':1234567,'isAvailable':True,'gameVersions':['26.3','NeoForge'],'fileLength':len(raw),'hashes':[{'algo':1,'value':entry['hashes']['sha1']}],'downloadUrl':'https://edge.forgecdn.net/files/123/fixture.jar'}
    monkeypatch.setattr(cp.sources,'CurseForge',Provider)
    result=cp.curseforge_record(None,entry,ACTIVE)
    assert result['client']=='required' and result['license']==license_name
    assert result['url'].startswith('https://edge.forgecdn.net/')
    entry['hashes']['sha1']='a'*40
    # Alter the provider-independent expected length to demonstrate fail-closed verification.
    entry['size']+=1
    with pytest.raises(ValueError,match='provider_mismatch'):cp.curseforge_record(None,entry,ACTIVE)

def test_pack_numbers_do_not_restart_after_archives_are_removed(pack_env):
    app,client,observed,calls=pack_env;st=app.state.store
    first=cp.build(st,app.state.rpc,1)
    with st.db() as db:db.execute('DELETE FROM client_packs')
    second=cp.build(st,app.state.rpc,1)
    assert first['version']==cp.__version__+'-client.1' and second['version']==cp.__version__+'-client.2'
    with st.db() as db:
        db.execute('DELETE FROM client_packs');db.execute("DELETE FROM settings WHERE name='client_pack_sequence'")
    st.event('mods','client_pack_created',1,{'number':6})
    third=cp.build(st,app.state.rpc,1)
    assert third['version']==cp.__version__+'-client.7'

def test_new_exporter_version_creates_new_pack_without_rewriting_legacy_archive(pack_env,monkeypatch):
    app,client,observed,calls=pack_env;st=app.state.store
    release=cp.__version__
    monkeypatch.setattr(cp,'__version__','0.1')
    observed['fingerprint']=cp.fingerprint(ACTIVE,observed['mods'])
    legacy=cp.build(st,app.state.rpc,1)
    path,_=cp.archive(st,legacy['id']);raw=path.read_bytes()
    monkeypatch.setattr(cp,'__version__',release)
    observed['fingerprint']=cp.fingerprint(ACTIVE,observed['mods'])
    current=cp.build(st,app.state.rpc,1)
    assert legacy['version']=='0.1-client.1'
    assert current['version']==release+'-client.2' and current['id']!=legacy['id']
    assert path.read_bytes()==raw
    assert cp.listing(st)['packs'][1]['manifest']['version']=='0.1-client.1'
    assert cp.build(st,app.state.rpc,1)['id']==current['id']

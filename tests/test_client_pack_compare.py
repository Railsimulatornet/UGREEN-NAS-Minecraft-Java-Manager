import copy,hashlib,json
import pytest
from mcj import client_pack_compare as compare,client_packs
from test_security import environment,enroll,post
from test_client_packs import pack_env

RUNTIME={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.97'}

def mod(name,version,sha,side='required'):
    return {'filename':name+'-'+version+'.jar','mods':[{'id':name.lower(),'name':name,'version':version}],'sha256':sha*64,'client':side}


def test_identity_based_mod_shader_and_runtime_diff_and_hash_only_patch():
    before={'runtime':RUNTIME,'mods':[mod('Shared','1','a'),mod('Removed','1','b'),mod('SecretServerGuard','1','c','unsupported')],
        'graphics':{'shader':'shader-1.zip','files':[{'path':'shaderpacks/shader-1.zip','hashes':{'sha256':'d'*64}}]}}
    after={'runtime':{**RUNTIME,'loader_version':'26.3.0.99'},'mods':[mod('Shared','2','e'),mod('Added','1','f')],
        'graphics':{'shader':'shader-2.zip','files':[{'path':'shaderpacks/shader-2.zip','hashes':{'sha256':'a'*64}}]}}
    value=compare.compare_manifests(before,after)
    assert [x['name'] for x in value['added']]==['Added']
    assert [x['name'] for x in value['removed']]==['Removed']
    assert {x['id'] for x in value['changed']}=={'mod:shared','shader:selected'} and value['runtime_changed']
    assert 'SecretServerGuard' not in json.dumps(value)
    same=copy.deepcopy(after);same['mods'][0]['sha256']='b'*64
    changed=compare.compare_manifests(after,same)
    assert len(changed['changed'])==1 and changed['changed'][0]['before']['version']==changed['changed'][0]['after']['version']=='2'
    assert compare.compare_manifests(after,after)['unchanged']==3


def test_compare_real_created_immutable_archives_and_reject_divergent_db_manifest(pack_env):
    app,client,observed,calls=pack_env;st=app.state.store
    first=client_packs.build(st,app.state.rpc,1)
    observed['mods'][0]['metadata']['mods'][0]['version']='2.0'
    observed['mods'][0]['hashes']=client_packs.hashes(b'fixture-updated-jar')
    observed['fingerprint']=client_packs.fingerprint(observed['runtime'],observed['mods'])
    second=client_packs.build(st,app.state.rpc,1)
    result=compare.compare(st,first['id'],second['id'])
    assert len(result['changed'])==1 and result['changed'][0]['before']['version']=='1.0' and result['changed'][0]['after']['version']=='2.0'
    assert 'VisitorGuard' not in json.dumps(result) and 'MUST-NOT-EXPORT' not in json.dumps(result)
    with st.db() as db:
        assert db.execute('SELECT COUNT(*) FROM client_packs').fetchone()[0]==2
        row=db.execute('SELECT manifest FROM client_packs WHERE id=?',(first['id'],)).fetchone();manifest=json.loads(row['manifest']);manifest['version']='forged'
        db.execute('UPDATE client_packs SET manifest=? WHERE id=?',(json.dumps(manifest),first['id']))
    with pytest.raises(ValueError,match='client_pack_integrity_failed'):compare.compare(st,first['id'],second['id'])


def test_catalog_reaches_older_packs_without_download_links(environment):
    app,client,credentials,mail=environment;enroll(environment);st=app.state.store
    with st.db() as db:
        for i in range(105):
            db.execute('INSERT INTO client_packs(id,number,created,actor,fingerprint,sha256,size,manifest) VALUES(?,?,?,?,?,?,?,?)',(format(i+1,'032x'),i+1,1700000000+i,1,'a'*64,'b'*64,1,json.dumps({'version':'test.'+str(i),'runtime':RUNTIME})))
    rows=[];cursor=None
    for _ in range(3):
        response=client.get('/api/client-packs/catalog',params={'before':cursor} if cursor else {})
        assert response.status_code==200;page=response.json();rows.extend(page['records']);cursor=page['next_cursor']
        if cursor is None:break
    assert len(rows)==105 and len({x['id'] for x in rows})==105
    assert not any(x in json.dumps(rows) for x in ['token','download','secret'])
    assert client.get('/api/client-packs/catalog',params={'before':0}).status_code==422
    with st.db() as db:db.execute('UPDATE client_packs SET manifest=? WHERE number=1',(json.dumps({'version':None,'runtime':RUNTIME}),))
    assert client.get('/api/client-packs/catalog',params={'before':2}).json()['detail']=='client_pack_manifest_invalid'


def test_comparison_api_requires_admin_and_rejects_invalid_ids(environment):
    app,client,credentials,mail=environment
    assert client.get('/api/client-packs/catalog').status_code==401
    assert client.get('/api/client-packs/compare',params={'before':'a'*32,'after':'b'*32}).status_code==401
    enroll(environment)
    assert client.get('/api/client-packs/compare',params={'before':'../escape','after':'b'*32}).status_code==409
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/client-packs/catalog').status_code==403


def test_duplicate_or_invalid_component_metadata_does_not_silently_compare():
    with pytest.raises(ValueError,match='client_pack_manifest_invalid'):compare.components({'mods':[mod('Duplicate','1','a'),mod('Duplicate','2','b')]})
    value=mod('Broken','1','a');value['mods'][0]['name']=None
    with pytest.raises(ValueError,match='client_pack_manifest_invalid'):compare.components({'mods':[value]})

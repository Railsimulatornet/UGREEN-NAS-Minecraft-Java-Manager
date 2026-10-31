import hashlib,io,json,zipfile
import httpx,pytest
from cryptography.fernet import Fernet
from mcj.store import Store
from mcj import mods

def jar(version):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        archive.writestr('fabric.mod.json',json.dumps({'schemaVersion':1,'id':'acceptance_update','version':version,
            'environment':'server','depends':{'minecraft':'26.3','java':'>=25','fabricloader':'>=0.20.1'}}))
    return stream.getvalue()

def prepare(tmp_path,enabled=False):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());store=Store(tmp_path/'state',key)
    (tmp_path/'staging').mkdir();old=mods.stage(store,tmp_path,jar('1.0.0'),'old.jar')
    available={'status':'available','modrinth_version_id':'New12345','project_id':'Proj1234','version':'1.1.0'}
    with store.db() as db:db.execute("UPDATE mods SET enabled=?,installed_enabled=?,state='installed',available=? WHERE id=?",(int(enabled),int(enabled),json.dumps(available),old['id']))
    return store,old

def provider(monkeypatch,raw,corrupt=False,game='26.3'):
    details={'id':'New12345','project_id':'Proj1234','version_type':'release','version_number':'1.1.0',
             'game_versions':[game],'loaders':['fabric'],'files':[{'primary':True,'filename':'new.jar','size':len(raw),
             'url':'https://cdn.modrinth.com/data/Proj1234/versions/New12345/new.jar','hashes':{'sha512':hashlib.sha512(raw).hexdigest()}}]}
    def handle(request):
        if request.url.host=='api.modrinth.com':return httpx.Response(200,json=details)
        return httpx.Response(200,content=(raw[:-1]+b'X') if corrupt else raw)
    original=httpx.Client
    monkeypatch.setattr(mods.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))

def test_update_stages_verified_file_without_installing_or_enabling_disabled_mod(tmp_path,monkeypatch):
    store,old=prepare(tmp_path);provider(monkeypatch,jar('1.1.0'))
    result=mods.stage_modrinth_update(store,tmp_path,old['id'])
    assert result['installed'] is False and result['enabled'] is False
    with store.db() as db:records=[dict(x) for x in db.execute('SELECT * FROM mods')]
    old_row=next(x for x in records if x['id']==old['id']);new=next(x for x in records if x['id']==result['id'])
    assert old_row['state']=='installed' and old_row['installed_enabled']==0
    assert new['state']=='staged' and new['replaces']==old['id']
    assert mods.proposed_records(records)==[new]
    assert not (tmp_path/'server').exists()

@pytest.mark.parametrize('corrupt,game,reason',[(True,'26.3','mod_download_hash_mismatch'),(False,'1.20.1','candidate_mod_dependencies_failed')])
def test_unverified_download_or_wrong_game_cannot_stage(tmp_path,monkeypatch,corrupt,game,reason):
    store,old=prepare(tmp_path,True);provider(monkeypatch,jar('1.1.0'),corrupt,game)
    with pytest.raises(ValueError,match=reason):mods.stage_modrinth_update(store,tmp_path,old['id'])
    with store.db() as db:assert db.execute('SELECT COUNT(*) FROM mods').fetchone()[0]==1

def test_loader_embedded_dependency_is_discovered_from_actual_artifact_metadata(tmp_path):
    from mcj.versions import ensure_loader_components,runtime_components
    store,old=prepare(tmp_path,True)
    nested=io.BytesIO()
    with zipfile.ZipFile(nested,'w') as archive:
        archive.writestr('fabric.mod.json',json.dumps({'id':'mixinextras','version':'0.5.5','provides':['com_github_llamalad7_mixinextras']}))
    loader=io.BytesIO()
    with zipfile.ZipFile(loader,'w') as archive:
        archive.writestr('fabric.mod.json',json.dumps({'id':'fabricloader','version':'0.20.1','jars':[{'file':'META-INF/jars/mixinextras.jar'}]}))
        archive.writestr('META-INF/jars/mixinextras.jar',nested.getvalue())
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=loader.getvalue()))) as client:
        proof=ensure_loader_components(store,'0.20.1',client)
    assert proof['components']['mixinextras']=='0.5.5' and proof['components']['com_github_llamalad7_mixinextras']=='0.5.5'
    config=runtime_components(store,store.get('server'))
    meta=mods.inspect_jar(jar('1.0.0'));meta['dependencies'].append({'id':'mixinextras','range':'>=0.5.5','mandatory':True})
    assert mods.dependency_report([{'id':'candidate','metadata':meta}],config)['structural_checks']=='passed'
    changed={**config,'loader_version':'0.20.2'}
    assert any(x['dependency']=='mixinextras' for x in mods.dependency_report([{'id':'candidate','metadata':meta}],changed)['issues'])

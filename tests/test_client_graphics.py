import copy,json,io,zipfile
import pytest
from mcj import client_packs as cp,client_graphics,mods,server_settings
from test_client_packs import pack_env,ACTIVE


def graphics():
 raw=b'iris-test';digest=cp.hashes(raw)
 return {'runtime':ACTIVE,'shader':'Complementary.zip','files':[
 {'path':'mods/iris.jar','hashes':digest,'fileSize':len(raw),'downloads':['https://cdn.modrinth.com/data/iris.jar'],'env':{'client':'required','server':'unsupported'},'metadata':{'loader':'NEOFORGE','mods':[{'id':'iris','name':'Iris','version':'1'}],'dependencies':[],'embedded':[]},'version':'1','evidence':'https://modrinth.com/mod/iris'},
 {'path':'shaderpacks/Complementary.zip','hashes':digest,'fileSize':len(raw),'downloads':['https://edge.forgecdn.net/files/1/2/Complementary.zip'],'env':{'client':'required','server':'unsupported'},'version':'test','evidence':'https://www.complementary.dev/'}]}


def test_graphics_export_official_references_and_separate_client_config(pack_env):
 app,client,observed,calls=pack_env;value=graphics();app.state.store.set('client_graphics',value);observed['graphics']=value;observed['fingerprint']=cp.fingerprint(ACTIVE,observed['mods'],value)
 result=cp.build(app.state.store,app.state.rpc,1);path,row=cp.archive(app.state.store,result['id'])
 with zipfile.ZipFile(path) as archive:
  index=json.loads(archive.read('modrinth.index.json'));assert index['files'][-1]['path']=='shaderpacks/Complementary.zip'
  assert archive.read('overrides/config/iris.properties')==b'enableShaders=true\nshaderPack=Complementary.zip\n'
  assert not any(x.endswith('Complementary.zip') for x in archive.namelist())
  assert b'Complementary Development' in archive.read('overrides/MCJ-LICENSES/Complementary-NOTICE.txt')
 assert observed['fingerprint']!=cp.fingerprint(ACTIVE,observed['mods'])


def test_graphics_changed_runtime_and_unsafe_files_blocked(pack_env):
 app,_,observed,_=pack_env;st=app.state.store;value=graphics();st.set('client_graphics',value)
 with pytest.raises(ValueError,match='runtime_changed'):client_graphics.approved(st,{**ACTIVE,'loader_version':'26.3.0.98'})
 value['files'][0]['downloads']=['https://attacker.invalid/file.jar'];st.set('client_graphics',value)
 with pytest.raises(ValueError,match='download_not_public'):client_graphics.approved(st,ACTIVE)


def test_dual_metadata_iris_uses_selected_neoforge_contract():
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w') as archive:
  archive.writestr('fabric.mod.json',json.dumps({'id':'iris','version':'1','depends':{'fabricloader':'>=0.12'}}))
  archive.writestr('META-INF/neoforge.mods.toml','modLoader="javafml"\nloaderVersion="[1,)"\nlicense="LGPL"\n[[mods]]\nmodId="iris"\nversion="1"\n')
 assert mods.inspect_jar(output.getvalue())['loader']=='FABRIC'
 assert mods.inspect_jar(output.getvalue(),preferred_loader='NEOFORGE')['loader']=='NEOFORGE'


def test_distance_rejects_silent_game_clamp():
 current={**ACTIVE,'properties':{}}
 for bad in ['64','0','NaN','31.5']:
  with pytest.raises(ValueError,match='chunk_distance'):server_settings.normalize(current,{'properties':{'view-distance':bad}})
 assert server_settings.normalize(current,{'properties':{'view-distance':'32'}})['properties']['view-distance']=='32'

from test_security import environment

def test_reviewed_create_iris_patch_replaces_only_client_copy(pack_env,monkeypatch):
 app,_,observed,_=pack_env;st=app.state.store;value=graphics();value['create_compatibility_patch']=cp.CREATE_IRIS_HASH;st.set('client_graphics',value);observed['graphics']=value
 original=copy.deepcopy(observed['mods'][0]);original.update(filename='create-original.jar',origin={'project_id':1651484},hashes={'sha1':'a'*40,'sha256':cp.CREATE_ORIGINAL_HASH,'sha512':'b'*128});original['metadata']['mods']=[{'id':'create','name':'Create','version':'6'}];observed['mods'].append(original);observed['fingerprint']=cp.fingerprint(ACTIVE,observed['mods'],value)
 previous=cp.classify
 monkeypatch.setattr(cp,'classify',lambda st,r,a:{'client':'required','url':'https://edge.forgecdn.net/files/1/2/create.jar'} if r['filename']=='create-original.jar' else previous(st,r,a))
 monkeypatch.setattr(cp,'create_assets',lambda st:{'path':'config/create-adapted/external-assets/create.jar','hashes':cp.hashes(b'asset'),'downloads':['https://edge.forgecdn.net/files/1/2/assets.jar'],'fileSize':5,'env':{'client':'required','server':'unsupported'}})
 result=cp.build(st,app.state.rpc,1);path,_=cp.archive(st,result['id'])
 with zipfile.ZipFile(path) as archive:
  raw=archive.read('overrides/mods/create-adapted-26.3-1.31-mcj-iris1.jar');assert cp.hashes(raw)['sha256']==cp.CREATE_IRIS_HASH
  assert 'overrides/MCJ-LICENSES/Create-Iris-Compatibility.java' in archive.namelist()
  assert not any(x['path']=='mods/create-original.jar' for x in json.loads(archive.read('modrinth.index.json'))['files'])
 assert observed['mods'][-1]['hashes']['sha256']==cp.CREATE_ORIGINAL_HASH

def test_standalone_shader_installer_is_rejected_before_server_staging(tmp_path):
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w') as archive:
  archive.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nMain-Class: net.hypercubemc.iris_installer.NewInstaller\n')
  archive.writestr('fabric.mod.json',json.dumps({'id':'complementaryinstaller','name':'Complementary Installer - FakeMod','version':'1.4.0'}))
 raw=output.getvalue();assert mods.inspect_jar(raw)['client_installer']
 with pytest.raises(ValueError,match='client_installer_not_server_mod'):mods.prepare_jar(None,tmp_path,raw,'Complementary-Installer-1.4.0.jar')
 assert not list(tmp_path.rglob('*.jar'))

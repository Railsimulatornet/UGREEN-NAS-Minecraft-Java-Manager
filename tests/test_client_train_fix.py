import copy
import hashlib
import json
import zipfile
import pytest
from mcj import client_packs as cp,client_train_fix as train
from test_client_packs import pack_env
from test_security import environment


def create_record():
    return {'filename':'create.jar','hashes':{'sha256':sorted(train.CREATE_HASHES)[0]},
            'metadata':{'mods':[{'id':'create','version':'6.0.11-adapted-1.31'}]}}


@pytest.mark.parametrize('case',['hash','runtime','create_missing','create_changed','duplicate'])
def test_exact_runtime_and_artifact_boundaries(case):
    graphics={'train_compatibility_patch':train.SHA256};active=copy.deepcopy(train.RUNTIME)
    selected=[create_record()]
    if case=='hash':graphics['train_compatibility_patch']='0'*64
    if case=='runtime':active['loader_version']='26.3.0.100'
    if case=='create_missing':selected=[]
    if case=='create_changed':selected[0]['hashes']['sha256']='0'*64
    if case=='duplicate':selected.append({'metadata':{'mods':[{'id':'mcj_create_train_fix'}]}})
    before=copy.deepcopy(selected);report=[];bundled={}
    with pytest.raises(ValueError,match='client_create_patch_unverified|client_graphics_duplicate'):
        train.bundle(graphics,active,selected,report,bundled)
    assert selected==before and not report and not bundled


def test_not_enabled_leaves_existing_exports_unchanged():
    selected=[create_record()];before=copy.deepcopy(selected)
    report=[];bundled={};train.bundle(None,train.RUNTIME,selected,report,bundled)
    assert selected==before and not report and not bundled


def test_client_archive_contains_only_accepted_companion_and_preserves_server_snapshot(pack_env):
    app,_,observed,_=pack_env;st=app.state.store
    observed['runtime']=copy.deepcopy(train.RUNTIME)
    st.set('server',{**train.RUNTIME,'properties':{},'world':'private'})
    create=observed['mods'][0]
    create['hashes']['sha256']=sorted(train.CREATE_HASHES)[0]
    create['metadata']['mods']=[{'id':'create','name':'Create','version':'6.0.11-adapted-1.31'}]
    before=copy.deepcopy(observed['mods'])
    graphics={'runtime':copy.deepcopy(train.RUNTIME),'shader':'fixture.zip',
        'train_compatibility_patch':train.SHA256,
        'files':[{'path':'shaderpacks/fixture.zip','hashes':cp.hashes(b'fixture'),'fileSize':7,
                  'downloads':['https://cdn.modrinth.com/data/fixture.zip'],
                  'env':{'client':'required','server':'unsupported'}}]}
    st.set('client_graphics',graphics);observed['graphics']=copy.deepcopy(graphics)
    observed['fingerprint']=cp.fingerprint(train.RUNTIME,observed['mods'],graphics)
    built=cp.build(st,app.state.rpc,1)
    path,row=cp.archive(st,built['id'])
    with zipfile.ZipFile(path)as archive:
        raw=archive.read('overrides/mods/'+train.FILENAME)
        assert hashlib.sha256(raw).hexdigest()==train.SHA256
        assert 'overrides/MCJ-LICENSES/Create-Train-Fix-1.0.4-LICENSE.txt' in archive.namelist()
        manifest=json.loads(archive.read('overrides/MCJ-CLIENT-PACK.json'))
        item=next(x for x in manifest['mods'] if x['filename']==train.FILENAME)
        assert item['client']=='required' and item['license']=='MIT'
        assert manifest['changes']['added'].count(train.FILENAME)==1
        index=json.loads(archive.read('modrinth.index.json'))
        assert not any(train.FILENAME in x['path'] for x in index['files'])
    assert observed['mods']==before
    assert cp.build(st,app.state.rpc,1)=={'id':built['id'],'already_current':True}

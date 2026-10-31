import hashlib,io,json,os,time,zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from cryptography.fernet import Fernet
from mcj.store import Store
from mcj import mods,packs,sources


def setup(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());st=Store(tmp_path/'state',key)
    st.set('server',{**st.get('server'),'version':'26.3','java':25,'loader':'FABRIC','loader_version':'0.20.1'})
    return st


def mod(version='1.0.0'):
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:
        z.writestr('fabric.mod.json',json.dumps({'id':'pack_sample','version':version,'environment':'server','depends':{'minecraft':'26.3'}}))
    return raw.getvalue()


def archive(tmp_path,files):
    path=tmp_path/'pack.zip'
    with zipfile.ZipFile(path,'w') as z:
        for name,raw in files.items():
            info=zipfile.ZipInfo();info.filename=name;z.writestr(info,raw)
    return path


def test_pack_configuration_is_staged_and_applies_only_to_disposable_candidate(tmp_path):
    st=setup(tmp_path);raw=mod()
    path=archive(tmp_path,{'server/mods/sample.jar':raw,'server/config/sample.json':b'{"text":"Gr\xc3\xbc\xc3\x9fe"}',
        'server/server.properties':b'pvp=false\nonline-mode=false\nrcon.password=NEVER_IMPORT\nlevel-name=forbidden\n',
        'server/world/level.dat':b'NEVER_IMPORT','server/.env':b'NEVER_IMPORT'})
    result=packs.stage_uploaded(st,tmp_path,path)
    assert result['live_server_changed'] is False and not (tmp_path/'server').exists()
    plan=result['pending_pack'];assert [x['path'] for x in plan['files']]==['config/sample.json']
    assert not plan['apply_properties'] and plan['properties']=={'pvp':'false'}
    data=tmp_path/'candidate';data.mkdir();runtime=st.get('server');old=json.dumps(runtime,sort_keys=True)
    installed=packs.apply_pending(st,tmp_path,data,runtime)
    assert json.dumps(runtime,sort_keys=True)==old
    assert (data/'config/sample.json').read_bytes()==b'{"text":"Gr\xc3\xbc\xc3\x9fe"}'
    assert not (data/'world').exists() and not (data/'.env').exists()
    assert installed and not st.get('pack_installations')


def test_pack_cannot_overwrite_independent_configuration(tmp_path):
    st=setup(tmp_path);path=archive(tmp_path,{'mods/sample.jar':mod(),'config/sample.json':b'pack'})
    packs.stage_uploaded(st,tmp_path,path)
    data=tmp_path/'candidate';(data/'config').mkdir(parents=True);(data/'config/sample.json').write_bytes(b'own')
    with pytest.raises(ValueError,match='pack_own_configuration_conflict'):packs.apply_pending(st,tmp_path,data,st.get('server'))
    assert (data/'config/sample.json').read_bytes()==b'own'


@pytest.mark.parametrize('name',['../escape','config/../../escape','C:/escape','config\\escape','/absolute','config/file:stream'])
def test_unsafe_pack_paths_fail_before_staging(tmp_path,name):
    st=setup(tmp_path);path=archive(tmp_path,{name:b'bad','mods/sample.jar':mod()})
    if os.name=='nt' and '\\' in name:
        # Windows ZipInfo normalizes separators when reading; exercise the Linux
        # boundary directly, where the original archive name is preserved.
        from types import SimpleNamespace
        info=zipfile.ZipInfo();info.filename=name
        with pytest.raises(ValueError,match='pack_unsafe_path'):packs.entries(SimpleNamespace(infolist=lambda:[info]))
    else:
        with pytest.raises(ValueError,match='pack_unsafe_path'):packs.stage_uploaded(st,tmp_path,path)
    assert not st.get('pack_pending')
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM mods').fetchone()[0]==0


def test_manifest_wrong_minecraft_and_malformed_types_are_rejected(tmp_path):
    st=setup(tmp_path)
    for value in [[],{'manifestType':'minecraftModpack','manifestVersion':1,'minecraft':{'version':'1.21.1'}}]:
        path=archive(tmp_path,{'manifest.json':json.dumps(value)})
        with pytest.raises(ValueError,match='pack_(manifest_invalid|game_mismatch)'):packs.stage_uploaded(st,tmp_path,path)


def test_pack_reimport_preserves_explicit_disabled_state(tmp_path):
    st=setup(tmp_path);raw=mod();path=archive(tmp_path,{'mods/sample.jar':raw})
    result=packs.stage_uploaded(st,tmp_path,path);identifier=result['staged'][0]['id']
    with st.db() as db:db.execute('UPDATE mods SET enabled=0 WHERE id=?',(identifier,))
    result=packs.stage_uploaded(st,tmp_path,path)
    assert result['staged'][0]['already_present'] and not result['staged'][0]['enabled']


def test_manual_mod_is_not_replaced_by_an_unrelated_pack(tmp_path):
    st=setup(tmp_path);original=mods.stage(st,tmp_path,mod(),'own.jar')
    path=archive(tmp_path,{'mods/sample.jar':mod('2.0.0')})
    with pytest.raises(ValueError,match='pack_own_mod_conflict'):packs.stage_uploaded(st,tmp_path,path)
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM mods').fetchone()[0]==1
    assert not st.get('pack_pending')


def test_drop_folder_preserves_original_and_does_not_repeat_events(tmp_path):
    st=setup(tmp_path);folder=tmp_path/'mods';folder.mkdir();path=folder/'sample.jar';original=mod();path.write_bytes(original)
    stamp=time.time()-10;os.utime(path,(stamp,stamp));mods.scan_drop_folder(st,tmp_path)
    assert path.exists() and path.read_bytes()==original
    with st.db() as db:before=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    mods.scan_drop_folder(st,tmp_path)
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==before


def test_approval_fingerprint_detects_mod_and_pack_changes_but_ignores_update_poll(tmp_path):
    st=setup(tmp_path);record=mods.stage(st,tmp_path,mod(),'sample.jar');initial=mods.fingerprint(st)
    with st.db() as db:db.execute('UPDATE mods SET available=? WHERE id=?',('{"status":"current"}',record['id']))
    assert mods.fingerprint(st)==initial
    with st.db() as db:db.execute('UPDATE mods SET enabled=0 WHERE id=?',(record['id'],))
    assert mods.fingerprint(st)!=initial
    changed=mods.fingerprint(st);st.set('pack_pending',[{'id':'pending'}]);assert mods.fingerprint(st)!=changed


def test_change_lock_is_reentrant_but_excludes_other_worker_threads(tmp_path):
    st=setup(tmp_path);other=Store(tmp_path/'state',tmp_path/'key')
    def attempt():
        with other.change_lock():return 'unexpected'
    with st.change_lock(),other.change_lock():
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(RuntimeError,match='maintenance_busy'):pool.submit(attempt).result()
    with other.change_lock():pass


def test_old_backup_cannot_inherit_newer_pack_tracking(tmp_path):
    assert packs.restored_state(tmp_path/'absent-pack-state.json')=={}


def test_pack_tracking_restore_validates_hashes_and_paths(tmp_path):
    path=tmp_path/'pack-state.json'
    value={'pack':{'name':'Pack','files':{'config/settings.json':'a'*64}}}
    path.write_text(json.dumps({'format':1,'installations':value}),encoding='utf-8')
    assert packs.restored_state(path)==value
    for name,digest in [('../outside','a'*64),('config/settings.json','invalid')]:
        path.write_text(json.dumps({'format':1,'installations':{'pack':{'files':{name:digest}}}}),encoding='utf-8')
        with pytest.raises(ValueError,match='pack_backup_state_invalid'):packs.restored_state(path)

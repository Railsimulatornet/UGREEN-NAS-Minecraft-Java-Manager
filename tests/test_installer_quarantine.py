import io,json,zipfile
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from mcj import mods,maintenance,packs,versions
from mcj.store import Store


def installer():
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        archive.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nMain-Class: net.hypercubemc.iris_installer.NewInstaller\n')
        archive.writestr('fabric.mod.json',json.dumps({'id':'complementaryinstaller','version':'1.4.0'}))
    return output.getvalue()


def record(identifier,metadata=None,**values):
    return {'id':identifier*64,'state':'installed','enabled':0,'installed_enabled':0,
            'metadata':metadata or {},'source':'upload','filename':'example.jar',**values}


@pytest.mark.parametrize('serialized',[False,True])
def test_new_candidates_exclude_installers_but_keep_ordinary_disabled_mods(serialized):
    meta=mods.inspect_jar(installer())
    bad=record('a',json.dumps(meta) if serialized else meta)
    normal=record('b')
    assert mods.proposed_records([bad,normal])==[normal]
    assert mods.selected_records([bad,normal],[normal['id']])==[normal]
    with pytest.raises(ValueError,match='client_installer_not_server_mod'):
        mods.selected_records([bad,normal],[bad['id']])


def test_quarantine_preserves_upload_identity_evidence_and_normal_disabled_mod(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());st=Store(tmp_path/'state',key)
    meta=mods.inspect_jar(installer());identifier=meta['sha256'];origin=json.dumps({'original':'upload'})
    with st.db() as db:
        db.execute("INSERT INTO mods(id,filename,sha256,metadata,source,state,enabled,installed_enabled,updated,origin,available) VALUES(?,?,?,?,?,'installed',0,0,0,?,?)",
                   (identifier,'Complementary-Installer-1.4.0.jar',identifier,json.dumps(meta),'upload',origin,'{}'))
        db.execute("INSERT INTO mods(id,filename,sha256,metadata,source,state,enabled,installed_enabled,updated) VALUES(?,?,?,?,?,'installed',0,0,0)",
                   ('b'*64,'normal.jar','b'*64,'{}','upload'))
        assert mods.quarantine_client_installers(db)==[identifier]
        assert mods.quarantine_client_installers(db)==[identifier]
        row=dict(db.execute('SELECT * FROM mods WHERE id=?',(identifier,)).fetchone())
        normal=dict(db.execute('SELECT * FROM mods WHERE id=?',('b'*64,)).fetchone())
    assert row['state']=='failed' and row['error']=='client_installer_not_server_mod'
    assert row['enabled']==row['installed_enabled']==0 and row['available'] is None
    assert row['origin']==origin and row['sha256']==identifier and json.loads(row['metadata'])==meta
    assert row['filename']=='Complementary-Installer-1.4.0.jar' and normal['state']=='installed'


@pytest.mark.parametrize('enabled',[False,True])
def test_restore_checks_actual_jar_and_never_restores_an_installer(tmp_path,monkeypatch,enabled):
    scratch=tmp_path/'candidate';data=scratch/'data';data.mkdir(parents=True)
    raw=installer();path=data/('mods' if enabled else 'mods-disabled')/'old-installer.jar';path.parent.mkdir();path.write_bytes(raw)
    original=tmp_path/'original-backup.jar';original.write_bytes(raw)
    (scratch/'runtime.json').write_text(json.dumps({'version':'26.3','loader':'NEOFORGE'}))
    monkeypatch.setattr(maintenance,'store',lambda c:object())
    monkeypatch.setattr(versions,'ensure_runtime_components',lambda st,runtime:runtime)
    monkeypatch.setattr(packs,'restored_state',lambda p:{})
    inspected=[]
    class ReachedDependencyCheck(Exception):pass
    def dependencies(rows,runtime):
        inspected.extend(rows)
        raise ReachedDependencyCheck()
    monkeypatch.setattr(mods,'dependency_report',dependencies)
    # Keep the extracted test candidate available for direct inspection after failure.
    monkeypatch.setattr(maintenance,'safe_remove',lambda c,p:None)
    controller=SimpleNamespace(extract_archive=lambda p:(scratch,data,{},None),trusted_guard=lambda *a:{'sha256':'g'*64})
    reason=ValueError if enabled else ReachedDependencyCheck
    with pytest.raises(reason):maintenance.candidate(controller,{'path':'fixture'}, {},'unused',restore=True)
    assert path.exists()==enabled and inspected==[] and original.read_bytes()==raw


def test_forged_catalog_metadata_cannot_copy_actual_installer_into_candidate(tmp_path,monkeypatch):
    scratch=tmp_path/'candidate';data=scratch/'data';data.mkdir(parents=True)
    (scratch/'runtime.json').write_text(json.dumps({'version':'26.3','loader':'NEOFORGE'}))
    raw=installer();row=record('a',{})
    monkeypatch.setattr(maintenance,'store',lambda c:object())
    monkeypatch.setattr(versions,'ensure_runtime_components',lambda st,runtime:runtime)
    monkeypatch.setattr(maintenance,'staged_bytes',lambda c,r:raw)
    monkeypatch.setattr(maintenance,'safe_remove',lambda c,p:None)
    controller=SimpleNamespace(extract_archive=lambda p:(scratch,data,{},None),trusted_guard=lambda *a:{'sha256':'g'*64})
    with pytest.raises(ValueError,match='client_installer_not_server_mod'):
        maintenance.candidate(controller,{'path':'fixture'},{},'unused',records=[row])
    assert not list(data.rglob('*.jar'))


def test_promotion_rejects_installer_before_any_live_mutation():
    with pytest.raises(ValueError,match='client_installer_not_server_mod'):
        maintenance.promote(None,{'mods':[record('a',mods.inspect_jar(installer()))]},None,None,None,'version')

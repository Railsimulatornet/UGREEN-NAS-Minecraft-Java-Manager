import importlib.util,json,os,stat,sys
from pathlib import Path
import pytest
from mcj import __version__
from mcj.first_login import consume_file
from test_security import environment,login,post

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
import ugos_prepare as gui


def env():return {'MCJ_PROJECT_DIR':'/volume1/docker/minecraftjava','MCJ_BACKUP_DIR':'/volume1/Backups/MinecraftJava','MCJ_WEB_ADDRESS':'https://minecraft.example.test','MCJ_ADMIN_NAME':'Owner','MCJ_ADMIN_EMAIL':'owner@example.test','MCJ_ACCEPT_EULA':'true'}


def test_gui_setup_demands_eula_https_and_explicit_new_paths():
    value=gui.settings(env());assert value['accept_eula'] and value['game_bind_address']=='127.0.0.1'
    for change in [{'MCJ_ACCEPT_EULA':'false'},{'MCJ_WEB_ADDRESS':'http://example.test'},{'MCJ_PROJECT_DIR':'/etc/other'},{'MCJ_PROJECT_DIR':'/volume1/docker/../other'},{'MCJ_PROXY_IPS':'0.0.0.0/0'}]:
        with pytest.raises(ValueError):gui.settings(env()|change)


def test_gui_setup_only_accepts_explicit_parent_binds_and_no_network():
    config=gui.settings(env());mounts=[{'Type':'bind','Source':str(Path(config[key]).parent),'Destination':str(Path(config[key]).parent),'RW':True} for key in ['root','backup_root']]
    # Path is platform-specific; deployment paths must be POSIX as on the NAS.
    own={'Mounts':mounts,'HostConfig':{'NetworkMode':'none'}};gui.validate_mounts(config,own)
    for bad in [dict(own,Mounts=mounts[:1]),dict(own,HostConfig={'NetworkMode':'host'}),dict(own,Mounts=[dict(x,RW=False) for x in mounts])]:
        with pytest.raises(RuntimeError):gui.validate_mounts(config,bad)


def test_prebuilt_image_must_match_running_container_and_verified_version():
    identifier='sha256:'+'a'*64;reference='railsimulatornet/ugreen-nas-minecraft-java-manager:'+__version__
    image={'Id':identifier,'Config':{'Labels':{'org.opencontainers.image.version':__version__,'org.opencontainers.image.revision':'b'*64}},'RepoDigests':[]}
    assert gui.image_identity(reference,{'Image':identifier},image)==identifier
    digest=reference.rsplit(':',1)[0]+'@sha256:'+'c'*64
    assert gui.image_identity(reference,{'Image':identifier},dict(image,RepoDigests=[digest]))==digest
    with pytest.raises(RuntimeError):gui.image_identity(reference,{'Image':'sha256:'+'d'*64},image)
    with pytest.raises(RuntimeError):gui.image_identity(reference,{'Image':identifier},dict(image,Config={'Labels':{}}))
    with pytest.raises(ValueError):gui.image_identity('bad image;echo secret',{'Image':identifier},image)


def test_first_password_change_removes_only_bound_initial_credential(environment,monkeypatch):
    app,client,credentials,_=environment;st=app.state.store
    path=st.state/'ERSTE-ANMELDUNG.txt';path.write_text('Disposable initial credential');st.set('gui_bootstrap',{'user_id':1,'credential_file_removed':False})
    csrf=login(environment)
    response=post(client,'/api/auth/password',{'current':credentials['Roman']['password'],'password':'GUI-New-Fixture-Password-2026!'},csrf)
    assert response.status_code==200 and not path.exists()
    assert st.get('gui_bootstrap')['credential_file_removed']


def test_other_user_or_regular_password_change_never_removes_file(environment):
    app,_,_,_=environment;st=app.state.store;path=st.state/'ERSTE-ANMELDUNG.txt';path.write_text('Fixture')
    st.set('gui_bootstrap',{'user_id':1,'credential_file_removed':False})
    consume_file(st,{'id':2,'force_password':True});assert path.exists()
    consume_file(st,{'id':1,'force_password':False});assert path.exists()


@pytest.mark.skipif(os.name=='nt',reason='Native Linux symlink and mode checks run separately')
def test_bootstrap_file_is_private_and_cleanup_refuses_symlinks(tmp_path,environment):
    config=gui.settings(env());root=tmp_path/'new';(root/'manager/state').mkdir(parents=True)
    # Avoid changing ownership in a non-root test runner.
    original=gui.os.chown;gui.os.chown=lambda *args:None
    try:path=gui.first_login_file(root,config,'Disposable-Fixture-Credential')
    finally:gui.os.chown=original
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    with pytest.raises(FileExistsError):gui.first_login_file(root,config,'Another-Fixture')
    app,_,_,_=environment;st=app.state.store;outside=tmp_path/'unrelated';outside.write_text('Keep');link=st.state/'ERSTE-ANMELDUNG.txt';link.symlink_to(outside)
    st.set('gui_bootstrap',{'user_id':1,'credential_file_removed':False});consume_file(st,{'id':1,'force_password':True})
    assert link.is_symlink() and outside.read_text()=='Keep'

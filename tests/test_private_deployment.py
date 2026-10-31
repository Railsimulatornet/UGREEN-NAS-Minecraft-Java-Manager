import io,json,os,stat,sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import browser_setup,deployment_snapshot
from mcj import bootstrap


def test_http_listener_has_no_docker_socket_or_nas_parent_mounts():
    context={'container':'a'*64,'base':'/volume1/docker/mcj-einrichtung','parents':['/volume1/docker'],'address':'192.168.1.50'}
    command=browser_setup.listener_command(context,'sha256:'+'b'*64)
    mounts=[command[i+1] for i,x in enumerate(command) if x=='-v']
    assert mounts==['/volume1/docker/mcj-einrichtung:/setup']
    assert command[command.index('--user')+1]=='1009:10'
    assert command[command.index('--network')+1]=='container:'+'a'*64
    assert '/var/run/docker.sock' not in ' '.join(command)


@pytest.mark.parametrize('action',['config','check','start_game','start_manager','down'])
def test_privileged_compose_uses_private_tmpfs_definition_and_environment(monkeypatch,tmp_path,action):
    captured={}
    def docker(*args,**kwargs):
        captured.update(args=args,request=json.loads(kwargs['input']))
        return SimpleNamespace(stdout='{}')
    monkeypatch.setattr(deployment_snapshot.install,'docker',docker)
    original='{"services":{"minecraft":{"image":"trusted"}}}'
    # A shared NAS file, even replaced after plan creation, is never opened by this boundary.
    shared=tmp_path/'docker-compose.yaml';shared.write_text('attacker-controlled replacement')
    deployment_snapshot.invoke('sha256:'+'b'*64,'/volume1/docker/new',original,'MCJ_GAME_MEMORY_MB=8192\n',action)
    command=captured['args'];request=captured['request']
    assert request['definition']==original and request['environment']=='MCJ_GAME_MEMORY_MB=8192\n'
    assert request['action']==action and request['project']==deployment_snapshot.install.PROJECT
    mounts=[command[i+1] for i,x in enumerate(command) if x=='-v']
    assert mounts==['/var/run/docker.sock:/var/run/docker.sock']
    assert '/volume1/docker/new:rw,nosuid,noexec,size=4m,mode=0700' in command
    assert '--network' in command and command[command.index('--network')+1]=='none'


def test_definition_helper_rejects_arbitrary_action_and_image_before_docker(monkeypatch):
    monkeypatch.setattr(deployment_snapshot.install,'docker',lambda *a,**k:pytest.fail('Docker must not be invoked'))
    for image,root,action in [('other:latest','/volume1/docker/new','down'),('sha256:'+'b'*64,'/etc/new','check'),('sha256:'+'b'*64,'/volume1/docker/new','exec')]:
        with pytest.raises(ValueError):deployment_snapshot.invoke(image,root,'{}','','check' if action=='check' else action)


def test_private_helper_preserves_canonical_config_and_working_directory(monkeypatch,tmp_path):
    request={'project':'mcj_disposable_test','root':str(tmp_path),'definition':'{"services":{}}','environment':'MCJ_GAME_MEMORY_MB=8192\n','action':'start_game'}
    monkeypatch.setattr(deployment_snapshot.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(request).encode())))
    output=io.BytesIO();monkeypatch.setattr(deployment_snapshot.sys,'stdout',SimpleNamespace(buffer=output))
    calls=[]
    def run(command,**kwargs):calls.append((command,kwargs));return SimpleNamespace(returncode=0,stdout=b'accepted')
    monkeypatch.setattr(deployment_snapshot.subprocess,'run',run)
    deployment_snapshot.main()
    command,kwargs=calls[0]
    assert command==['docker','compose','-p','mcj_disposable_test','--project-directory',str(tmp_path),'--env-file',str(tmp_path/'.env'),'-f',str(tmp_path/'docker-compose.yaml'),'up','-d','controller','minecraft']
    assert kwargs['cwd']==tmp_path and kwargs['env']=={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp'}
    assert (tmp_path/'docker-compose.yaml').read_text()==request['definition']
    assert (tmp_path/'.env').read_text()==request['environment']
    assert output.getvalue()==b'accepted'


@pytest.mark.skipif(os.name=='nt',reason='Requires POSIX no-follow and descriptor permission operations')
def test_listener_temp_swap_cannot_change_external_permissions_or_ownership(monkeypatch,tmp_path):
    base=tmp_path/'queue';base.mkdir();outside=tmp_path/'unrelated';outside.write_bytes(b'keep');outside.chmod(0o600)
    before=outside.stat();original=Path.open
    monkeypatch.setattr(bootstrap.secrets,'token_hex',lambda _: 'controlled')
    class ReplaceAfterClose:
        def __init__(self,path):self.path=path;self.stream=original(path,'xb')
        def __enter__(self):return self.stream.__enter__()
        def __exit__(self,*args):
            self.stream.__exit__(*args);self.path.unlink();self.path.symlink_to(outside)
    def opened(path,*args,**kwargs):
        if path==base/'status.json.controlled':return ReplaceAfterClose(path)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    bootstrap.atomic(base/'status.json',b'{}',0o640,owner=(os.getuid(),os.getgid()))
    after=outside.stat()
    assert (after.st_mode,after.st_uid,after.st_gid)==(before.st_mode,before.st_uid,before.st_gid)
    assert outside.read_bytes()==b'keep'
    with pytest.raises((OSError,ValueError)):bootstrap.read_regular(base/'status.json')

"""Fabric's thin launcher must finish installation before the offline test."""
from types import SimpleNamespace

import pytest

from mcj.maintenance import prepare_dependencies


@pytest.mark.parametrize('minecraft', ['1.20.1', '1.21.1', '26.3'])
@pytest.mark.parametrize('preparation_exit', [0, 1])
def test_cross_loader_candidate_prepares_fabric_without_user_mods(tmp_path, monkeypatch, minecraft, preparation_exit):
    monkeypatch.setenv('HOST_PROJECT_ROOT', str(tmp_path))
    scratch=tmp_path/'candidate';data=scratch/'data';(data/'mods').mkdir(parents=True)
    (data/'mods/user.jar').write_bytes(b'user mod must not run during downloads')
    (data/'server.properties').write_text('level-name=existing-world\n')
    (data/'existing-world').mkdir();(data/'existing-world/level.dat').write_bytes(b'original world')
    cached=data/'.fabric/server';cached.mkdir(parents=True);(cached/'old-launcher.jar').write_bytes(b'old cached executable')
    events=[];runs=[]
    class Container:
        status='exited'
        def __init__(self,code):self.code=code
        def wait(self,timeout):assert timeout==300;return {'StatusCode':self.code}
        def reload(self):pass
        def remove(self,**kwargs):events.append('removed')
    def run(image,**kwargs):
        assert not list((data/'mods').iterdir()) and (scratch/'mods-during-setup/user.jar').is_file()
        assert not cached.exists()
        assert kwargs['network']=='setup-network' and 'ports' not in kwargs
        assert kwargs['cap_drop']==['ALL'] and kwargs['security_opt']==['no-new-privileges:true']
        runs.append(kwargs)
        if len(runs)==1:
            assert kwargs['environment']['SETUP_ONLY']=='true'
            assert kwargs['environment']['FABRIC_FORCE_REINSTALL']=='true'
            return Container(0)
        assert kwargs['entrypoint']==['java'] and kwargs['command'][-1]=='--help'
        assert kwargs['command'][2]=='fabric-server-mc.'+minecraft+'-loader.0.20.1-launcher.1.1.2.jar'
        if preparation_exit==0:
            library=data/'libraries/net/fabricmc/fabric-loader/0.20.1/fabric-loader-0.20.1.jar'
            library.parent.mkdir(parents=True);library.write_bytes(b'official loader library')
        return Container(preparation_exit)
    network=SimpleNamespace(name='setup-network',remove=lambda:events.append('network removed'))
    controller=SimpleNamespace(ROOT=tmp_path,PROJECT='fixture',client=SimpleNamespace(
        networks=SimpleNamespace(create=lambda *args,**kwargs:network),containers=SimpleNamespace(run=run)))
    configuration={'loader':'FABRIC','version':minecraft,'loader_version':'0.20.1','installer_version':'1.1.2'}
    if preparation_exit:
        with pytest.raises(RuntimeError,match='runtime_dependency_setup_failed'):
            prepare_dependencies(controller,scratch,data,configuration,'pinned-image')
    else:
        prepare_dependencies(controller,scratch,data,configuration,'pinned-image')
        assert (data/'libraries/net/fabricmc/fabric-loader/0.20.1/fabric-loader-0.20.1.jar').is_file()
    assert len(runs)==2 and events==['removed','removed','network removed']
    assert (data/'mods/user.jar').read_bytes()==b'user mod must not run during downloads'
    assert (data/'existing-world/level.dat').read_bytes()==b'original world'
    assert (data/'server.properties').read_text()=='level-name=existing-world\n'


def test_fabric_preparation_refuses_a_linked_install_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('HOST_PROJECT_ROOT',str(tmp_path))
    scratch=tmp_path/'candidate';data=scratch/'data';(data/'mods').mkdir(parents=True)
    outside=tmp_path/'outside';outside.mkdir();(outside/'untouched').write_bytes(b'original')
    (data/'.fabric').mkdir()
    try:(data/'.fabric/server').symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('Symbolic links require an enabled Windows privilege')
    calls=[]
    controller=SimpleNamespace(ROOT=tmp_path,PROJECT='fixture',client=SimpleNamespace(
        networks=SimpleNamespace(create=lambda *args,**kwargs:SimpleNamespace(name='setup',remove=lambda:calls.append('network removed'))),
        containers=SimpleNamespace(run=lambda *args,**kwargs:pytest.fail('No process may use the linked cache'))))
    with pytest.raises(ValueError,match='unsafe_fabric_install_cache'):
        prepare_dependencies(controller,scratch,data,{'loader':'FABRIC','version':'1.21.1','loader_version':'0.20.1'},'image')
    assert (outside/'untouched').read_bytes()==b'original' and calls==['network removed']


@pytest.mark.parametrize('field',['version','loader_version','installer_version'])
def test_fabric_launcher_name_cannot_select_an_archive_path(tmp_path, field):
    configuration={'loader':'FABRIC','version':'1.21.1','loader_version':'0.20.1','installer_version':'1.1.2'}
    configuration[field]='../../untrusted'
    with pytest.raises(ValueError,match='runtime_dependency_setup_failed'):
        prepare_dependencies(SimpleNamespace(),tmp_path,tmp_path,configuration,'image')

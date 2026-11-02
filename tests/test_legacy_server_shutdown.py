"""Older runner deadlines must not force-kill a slow world save."""
import json
from types import SimpleNamespace

import pytest

from mcj import server_shutdown as shutdown


class Container:
    id='a'*64
    status='running'
    def __init__(self,duration=b'60s'):
        self.arguments=b'mc-server-runner\0--stop-duration\0'+duration+b'\0java\0'
        self.attrs={'HostConfig':{'RestartPolicy':{'Name':'unless-stopped','MaximumRetryCount':0}},'State':{'ExitCode':0}}
        self.events=[];self.remaining=None
    def exec_run(self,arguments):
        assert arguments==['cat','/proc/1/cmdline']
        self.events.append('inspect runner');return SimpleNamespace(exit_code=0,output=self.arguments)
    def reload(self):
        if self.remaining is not None:
            self.remaining-=1
            if self.remaining<=0:self.status='exited'
    def update(self,*,restart_policy):
        self.events.append(('policy',dict(restart_policy)));self.attrs['HostConfig']['RestartPolicy']=dict(restart_policy)


def manual_stop(monkeypatch,container):
    def stop(value):
        assert value is container and value.status=='exited'
        assert shutdown.policy(container)=={'Name':'no','MaximumRetryCount':0}
        container.events.append('manual stop after clean exit')
    monkeypatch.setattr(shutdown,'stop_container',stop)
    monkeypatch.setattr(shutdown.time,'sleep',lambda seconds:None)


@pytest.mark.parametrize('rcon_closed',[False,True])
def test_old_runner_finishes_saving_before_any_docker_stop(tmp_path,monkeypatch,rcon_closed):
    container=Container();manual_stop(monkeypatch,container)
    def command(value):
        assert value=='stop' and shutdown.policy(container)['Name']=='no'
        assert shutdown.journal(tmp_path).is_file()
        container.events.append('RCON stop');container.remaining=3
        if rcon_closed:raise ConnectionError('RCON connection closed')
    assert shutdown.stop_legacy(tmp_path,container,command) is True
    assert container.status=='exited' and shutdown.policy(container)['Name']=='unless-stopped'
    assert container.events==['inspect runner',('policy',{'Name':'no','MaximumRetryCount':0}),'RCON stop',
        'manual stop after clean exit',('policy',{'Name':'unless-stopped','MaximumRetryCount':0})]
    assert not shutdown.journal(tmp_path).exists()


@pytest.mark.parametrize('duration',[b'0s',b'0.0s'])
def test_current_runner_keeps_the_existing_docker_stop_path(tmp_path,duration):
    container=Container(duration)
    assert shutdown.stop_legacy(tmp_path,container,lambda _:pytest.fail('No RCON change for the current runner')) is False
    assert container.events==['inspect runner'] and not shutdown.journal(tmp_path).exists()


@pytest.mark.parametrize('init',[b'/sbin/docker-init',b'/usr/bin/tini'])
@pytest.mark.parametrize('duration,expected',[(b'60s',True),(b'0s',False)])
def test_compose_init_wrapper_is_followed_to_the_real_runner(init,duration,expected):
    container=Container(duration)
    def read(command):
        outputs={'/proc/1/cmdline':init+b'\0--\0/bin/bash\0/mcj/start.sh\0',
                 '/proc/1/task/1/children':b'7 ', '/proc/7/cmdline':container.arguments}
        assert command[0]=='cat';return SimpleNamespace(exit_code=0,output=outputs[command[1]])
    container.exec_run=read
    assert shutdown.legacy_runner(container) is expected


def test_ambiguous_init_children_are_not_used_to_choose_a_stop_target():
    container=Container()
    def read(command):
        outputs={'/proc/1/cmdline':b'/sbin/docker-init\0', '/proc/1/task/1/children':b'7 8',
                 '/proc/7/cmdline':container.arguments,'/proc/8/cmdline':container.arguments}
        return SimpleNamespace(exit_code=0,output=outputs[command[1]])
    container.exec_run=read
    with pytest.raises(RuntimeError,match='server_shutdown_runtime_unverified'):shutdown.legacy_runner(container)


@pytest.mark.parametrize('arguments',[
    b'other-server\x00--stop-duration\x0060s\x00',b'mc-server-runner\x00java\x00',
    b'mc-server-runner\x00--stop-duration\x0060s\x00--stop-duration\x000s\x00',
    b'mc-server-runner\0--stop-duration\0unexpected\0',
])
def test_unknown_process_or_deadline_is_refused_without_changing_policy(tmp_path,arguments):
    container=Container();container.arguments=arguments
    with pytest.raises(RuntimeError,match='server_shutdown_runtime_unverified'):
        shutdown.stop_legacy(tmp_path,container,lambda _:pytest.fail('No unverified stop'))
    assert len(container.events)==1 and shutdown.policy(container)['Name']=='unless-stopped'
    assert not shutdown.journal(tmp_path).exists()


def test_timeout_never_forces_a_running_server_to_exit(tmp_path,monkeypatch):
    container=Container();manual_stop(monkeypatch,container)
    clock=iter([0,601]);monkeypatch.setattr(shutdown.time,'monotonic',lambda:next(clock))
    with pytest.raises(RuntimeError,match='shutdown_pending_no_forced_kill'):
        shutdown.stop_legacy(tmp_path,container,lambda _:None)
    assert container.status=='running' and shutdown.policy(container)['Name']=='unless-stopped'
    assert 'manual stop after clean exit' not in container.events
    assert not shutdown.journal(tmp_path).exists()


def test_rejected_rcon_restores_the_original_policy(tmp_path):
    container=Container()
    def command(_):raise RuntimeError('RCON authentication rejected')
    with pytest.raises(RuntimeError,match='RCON authentication rejected'):
        shutdown.stop_legacy(tmp_path,container,command)
    assert container.status=='running' and shutdown.policy(container)['Name']=='unless-stopped'
    assert not shutdown.journal(tmp_path).exists()


def saved_policy(tmp_path,container,**changes):
    path=shutdown.journal(tmp_path);path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'container_id':container.id,'restart_policy':{'Name':'unless-stopped','MaximumRetryCount':0},**changes}))
    return path


@pytest.mark.parametrize('status',['running','exited'])
def test_controller_restart_recovers_a_durable_policy_journal(tmp_path,status):
    container=Container();container.status=status
    path=saved_policy(tmp_path,container);container.attrs['HostConfig']['RestartPolicy']={'Name':'no','MaximumRetryCount':0}
    assert shutdown.recover(tmp_path,container) is True
    assert shutdown.policy(container)['Name']=='unless-stopped' and not path.exists()
    assert container.status==status and container.events==[('policy',{'Name':'unless-stopped','MaximumRetryCount':0})]


@pytest.mark.parametrize('problem',['other_container','externally_changed_policy','invalid_saved_policy'])
def test_recovery_refuses_an_unrelated_or_changed_container(tmp_path,problem):
    container=Container();changes={}
    if problem=='other_container':changes['container_id']='b'*64
    if problem=='invalid_saved_policy':changes['restart_policy']={'Name':'untrusted','MaximumRetryCount':0}
    path=saved_policy(tmp_path,container,**changes)
    if problem=='externally_changed_policy':container.attrs['HostConfig']['RestartPolicy']={'Name':'always','MaximumRetryCount':0}
    with pytest.raises(RuntimeError):shutdown.recover(tmp_path,container)
    assert path.exists() and container.events==[]

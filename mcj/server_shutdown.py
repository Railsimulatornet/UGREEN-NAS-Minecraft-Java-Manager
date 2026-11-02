"""Stop an older runner without activating its internal force-kill deadline."""
import json
import re
import time

from .infrastructure import stop_container
from .project_paths import project_path
from .store import Store


def journal(root):
    path=project_path(root,'control/runtime/shutdown-policy.json')
    if path.resolve()!=path.absolute():raise RuntimeError('shutdown_recovery_path_invalid')
    return path


def policy_value(value):
    name=value.get('Name') or 'no';count=value.get('MaximumRetryCount',0)
    if name not in {'no','always','unless-stopped','on-failure'} or type(count) is not int or not 0<=count<=1000000:
        raise RuntimeError('shutdown_restart_policy_invalid')
    return {'Name':name,'MaximumRetryCount':count}


def policy(container):
    return policy_value(container.attrs['HostConfig']['RestartPolicy'])


def recover(root,container):
    """Restore an interrupted temporary policy change on the same container only."""
    path=journal(root)
    if not path.exists():return False
    if not path.is_file() or path.stat().st_size>8192:raise RuntimeError('shutdown_recovery_invalid')
    value=json.loads(path.read_text())
    if value.get('container_id')!=container.id or not re.fullmatch('[0-9a-f]{64}',container.id):
        raise RuntimeError('shutdown_recovery_identity_mismatch')
    saved=value.get('restart_policy')
    if not isinstance(saved,dict) or set(saved)!={'Name','MaximumRetryCount'}:
        raise RuntimeError('shutdown_recovery_invalid')
    original=policy_value(saved)
    container.reload();current=policy(container)
    if current not in (original,{'Name':'no','MaximumRetryCount':0}):
        raise RuntimeError('shutdown_restart_policy_changed')
    if current!=original:container.update(restart_policy=original)
    container.reload()
    if policy(container)!=original:raise RuntimeError('shutdown_restart_policy_not_restored')
    path.unlink()
    return True


def arguments(container,pid):
    result=container.exec_run(['cat','/proc/'+str(pid)+'/cmdline'])
    if result.exit_code!=0 or not 0<len(result.output)<=65536:
        raise RuntimeError('server_shutdown_runtime_unverified')
    return result.output.rstrip(b'\0').split(b'\0')


def legacy_runner(container):
    values=arguments(container,1)
    if values[0].rsplit(b'/',1)[-1] in {b'docker-init',b'tini',b'tini-static'}:
        children=container.exec_run(['cat','/proc/1/task/1/children'])
        if children.exit_code!=0 or len(children.output)>4096:
            raise RuntimeError('server_shutdown_runtime_unverified')
        pids=children.output.split()
        if not 0<len(pids)<=64 or any(not p.isdigit() or not 1<int(p)<2**31 for p in pids):
            raise RuntimeError('server_shutdown_runtime_unverified')
        candidates=[arguments(container,int(pid)) for pid in pids]
        runners=[value for value in candidates if value[0].rsplit(b'/',1)[-1]==b'mc-server-runner']
        if len(runners)!=1:raise RuntimeError('server_shutdown_runtime_unverified')
        values=runners[0]
    if values[0].rsplit(b'/',1)[-1]!=b'mc-server-runner':
        raise RuntimeError('server_shutdown_runtime_unverified')
    arguments_=values
    values=[]
    for index,argument in enumerate(arguments_):
        if argument==b'--stop-duration' and index+1<len(arguments_):values.append(arguments_[index+1])
        elif argument.startswith(b'--stop-duration='):values.append(argument.split(b'=',1)[1])
    if len(values)!=1 or not re.fullmatch(rb'\d+(?:\.\d+)?(?:ns|us|ms|s|m|h)',values[0]):
        raise RuntimeError('server_shutdown_runtime_unverified')
    return float(re.sub(rb'[a-z]+$',b'',values[0]))>0


def stop_legacy(root,container,command):
    if not re.fullmatch('[0-9a-f]{64}',container.id):raise ValueError('container_identity_invalid')
    recover(root,container)
    if not legacy_runner(container):return False
    original=policy(container);path=journal(root)
    Store.atomic(path,json.dumps({'container_id':container.id,'restart_policy':original}).encode(),0o600)
    try:
        container.update(restart_policy={'Name':'no','MaximumRetryCount':0})
        try:command('stop')
        except (OSError,ConnectionError):
            # Minecraft can close RCON before acknowledging its stop command.
            # Completion still requires a clean process exit below.
            pass
        deadline=time.monotonic()+600
        while True:
            container.reload()
            if container.status=='exited':break
            if time.monotonic()>=deadline:raise RuntimeError('shutdown_pending_no_forced_kill')
            time.sleep(1)
        if container.attrs['State']['ExitCode']!=0:raise RuntimeError('unclean_server_shutdown')
        stop_container(container)
        return True
    finally:
        recover(root,container)

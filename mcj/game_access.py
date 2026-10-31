"""Hot-reloaded game admission, acknowledged by the current protection mod."""
import hashlib,json,time
from .project_paths import project_path
from .store import Store

def policy_path(root):return project_path(root,'control/roles/network-access.json')
def read(root,container_id,started_at=0):
    path=policy_path(root);raw=None
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.stat().st_size>4096:raise ValueError('invalid_game_access_policy')
        raw=path.read_bytes()
    value=True if raw is None else json.loads(raw)['public_game']
    if type(value) is not bool:raise ValueError('invalid_game_access_policy')
    fingerprint='legacy' if raw is None else hashlib.sha256(raw).hexdigest()
    try:
        report_path=project_path(root,'control/reports/guard-status.json')
        if report_path.is_symlink() or report_path.stat().st_size>65536:raise ValueError()
        report=json.loads(report_path.read_bytes())
        ready=bool(started_at<=report['at']<=time.time() and time.time()-report['at']<15 and report.get('network_access_protocol')=='mcj_network_v1'
                   and report.get('public_game') is value and report.get('network_access_fingerprint')==fingerprint)
    except (OSError,ValueError,KeyError,TypeError):ready=False
    basis=hashlib.sha256(json.dumps([container_id,fingerprint,value],separators=(',',':')).encode()).hexdigest()
    return {'public_game':value,'ready':ready,'basis':basis,'fingerprint':fingerprint}

def change(root,container_id,desired,expected,started_at=0):
    if type(desired) is not bool:raise ValueError('invalid_setting')
    current=read(root,container_id,started_at)
    if current['basis']!=expected:raise ValueError('game_access_changed')
    if not current['ready']:raise ValueError('game_access_guard_update_required')
    path=policy_path(root);previous=path.read_bytes() if path.exists() else None
    raw=json.dumps({'public_game':desired},separators=(',',':')).encode()
    Store.atomic(path,raw,0o640)
    try:
        for _ in range(25):
            result=read(root,container_id,started_at)
            if result['ready'] and result['public_game'] is desired:
                return {**result,'acknowledged':True,'restart_required':False}
            time.sleep(.2)
        raise ValueError('game_access_acknowledgement_missing')
    except BaseException:
        if previous is None:path.unlink()
        else:Store.atomic(path,previous,0o640)
        raise

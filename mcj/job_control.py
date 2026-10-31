"""Durable operation identities, Berlin scheduling and truthful progress."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import time

_job = ContextVar('mcj_job', default=None)
_disconnect = ContextVar('mcj_disconnect', default=False)


def berlin_timestamp(value):
    try:
        local = datetime.strptime(value, '%Y-%m-%dT%H:%M')
        zone = ZoneInfo('Europe/Berlin')
        options = {local.replace(tzinfo=zone, fold=fold).timestamp() for fold in (0, 1)
                   if datetime.fromtimestamp(local.replace(tzinfo=zone, fold=fold).timestamp(), zone).replace(tzinfo=None) == local}
        if len(options) != 1:
            raise ValueError()
        stamp = options.pop()
        if not time.time() < stamp <= time.time() + 366 * 86400:
            raise ValueError()
        return stamp
    except (ValueError, TypeError):
        raise ValueError('invalid_berlin_schedule') from None


def purpose(current, configuration):
    if any(current.get(k) != configuration.get(k) for k in ('version', 'java', 'loader', 'loader_version')):
        return 'version'
    if current.get('properties', {}).get('level-name', current.get('world', 'world')) != configuration.get('properties', {}).get('level-name', configuration.get('world', 'world')):
        return 'world'
    return 'settings'


@contextmanager
def operation(store, identifier):
    token = _job.set((store, identifier))
    allowed=False
    if identifier:
        with store.db() as db:
            row=db.execute("SELECT j.mode,j.state,j.approved,u.enabled,u.admin FROM jobs j JOIN users u ON u.id=j.actor WHERE j.id=?",(identifier,)).fetchone()
        allowed=bool(row and row['mode']=='immediate' and row['state']=='running' and row['approved'] and row['enabled'] and row['admin'])
    disconnect_token=_disconnect.set(allowed)
    try:
        phase('preparing')
        yield
    finally:
        _disconnect.reset(disconnect_token)
        _job.reset(token)


def may_disconnect_players():
    return _disconnect.get()


def dependency_failure(report, records):
    """Retain the specific, bounded check failure across controller RPC errors."""
    context=_job.get()
    if not context or not context[1]:return
    store,identifier=context
    names={row['id']:str(row.get('filename',row['id']))[:256] for row in records}
    issues=[{**{k:str(v)[:500] for k,v in issue.items() if k in ('id','issue','dependency','actual','required')},
             'filename':names.get(issue.get('id'),'')} for issue in report.get('issues',[])[:100]]
    with store.db(immediate=True) as db:
        row=db.execute("SELECT result FROM jobs WHERE id=? AND state='running'",(identifier,)).fetchone()
        if not row:return
        result=json.loads(row['result'] or '{}');result['dependency_report']={'issues':issues}
        db.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(result),identifier))


def phase(stage):
    context = _job.get()
    if not context or not context[1]:
        return
    store, identifier = context
    now = time.time()
    with store.db(immediate=True) as db:
        row = db.execute('SELECT result,updated FROM jobs WHERE id=? AND state=\'running\'', (identifier,)).fetchone()
        if not row:
            return
        previous = json.loads(row['result']) if row['result'] else {}
        history = previous.get('phases', [])
        if not history or history[-1]['stage'] != stage:
            history.append({'stage': stage, 'at': now})
        db.execute('UPDATE jobs SET result=?,updated=? WHERE id=?',
                   (json.dumps({'progress': stage, 'started': previous.get('started', now), 'phases': history}), now, identifier))


def identity(db, kind, payload):
    payload={k:v for k,v in payload.items() if k!='_scheduled_at'}
    if kind in ('version_test','version_apply'):
        plan=db.execute('SELECT configuration,based_on,mod_fingerprint FROM version_plans WHERE id=?',(payload.get('id'),)).fetchone()
        if plan:payload={k:plan[k] for k in ('configuration','based_on','mod_fingerprint')}
    return json.dumps(payload,sort_keys=True)


def deduplicate_pending(store):
    """Retain the original request; collapse redundant pre-upgrade queued copies."""
    removed=[];seen={}
    with store.db(immediate=True) as db:
        for row in db.execute("SELECT id,kind,payload FROM jobs WHERE state IN ('planned','queued') ORDER BY created,id").fetchall():
            key=(row['kind'],identity(db,row['kind'],json.loads(row['payload'])))
            if key not in seen:
                seen[key]=row['id'];continue
            db.execute("UPDATE jobs SET state='cancelled',updated=?,result=? WHERE id=?",
                       (time.time(),json.dumps({'reason':'duplicate_job_cancelled','original_job':seen[key]}),row['id']))
            removed.append(row['id'])
    if removed:store.event('maintenance','duplicate_jobs_cancelled',data={'ids':removed})
    return removed


def deployment_held(store,now=None):
    """Short root-created deployment lease; never pause queued work indefinitely."""
    import math,os,stat
    now=time.time() if now is None else now;path=store.state/'.deployment-hold.json'
    try:info=path.stat(follow_symlinks=False)
    except FileNotFoundError:return False
    except OSError:return False
    recent=0<=now-info.st_mtime<300
    if not recent:return False
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>1024:return recent
    fd=None
    try:
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0));raw=os.read(fd,1025)
        value=json.loads(raw);until=value.get('until')
        if type(until) not in [int,float] or not math.isfinite(until) or until>now+300:return recent
        return now<until
    except (OSError,ValueError,TypeError,AttributeError):return recent
    finally:
        if fd is not None:os.close(fd)

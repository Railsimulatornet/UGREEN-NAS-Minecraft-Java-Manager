"""Describe actual protection and enqueue at most one automatic backup."""
import json
import time

def _future(row,now):
    return bool(row and row['state']!='running' and row['mode']=='scheduled'
                and isinstance(row.get('scheduled_at'),(int,float)) and row['scheduled_at']>now)

def status(store,server=None,now=None,backup_root=None):
    now=time.time() if now is None else now
    cfg=store.get('maintenance');interval=cfg.get('backup_minutes',30)*60
    started=store.get('backup_schedule_started_at')
    if not isinstance(started,(int,float)):started=now
    with store.db() as db:
        successful=db.execute("SELECT MAX(created) FROM backups WHERE state='verified'").fetchone()[0]
        latest=db.execute("SELECT * FROM backups WHERE state='verified' ORDER BY created DESC LIMIT 1").fetchone()
        attempt=db.execute("SELECT MAX(updated) FROM jobs WHERE kind='backup' AND state IN ('failed','interrupted')").fetchone()[0]
        pending=[dict(x) for x in db.execute("SELECT id,state,mode,created,updated,payload FROM jobs WHERE kind='backup' AND approved=1 AND state IN ('queued','running') ORDER BY created,id")]
    for row in pending:row['scheduled_at']=json.loads(row.pop('payload')).get('_scheduled_at')
    pending.sort(key=lambda row:(row['state']!='running',_future(row,now),row['created'],row['id']))
    row=pending[0] if pending else None
    due=(successful if successful is not None else started)+interval
    retry=max(due,(attempt or 0)+interval) if not row or _future(row,now) else None
    wait=None
    if row:
        if row['state']=='running':wait='running'
        elif _future(row,now):wait='scheduled'
        elif row['mode'] in ('idle_5min','idle_now','scheduled'):
            count=(server or {}).get('players_online')
            wait='status_unknown' if count is None else 'players_online' if count else 'continuous_idle' if row['mode']=='idle_5min' else 'queued'
        else:wait='queued'
    available=None
    if latest and backup_root is not None:
        from .backup_inventory import archive_info
        available=archive_info(backup_root,dict(latest))['archive_available']
    return {'enabled':cfg.get('backup_enabled',False),'last_success':successful,'last_archive_available':available,'age_seconds':None if successful is None else max(0,now-successful),
            'due_at':due,'retry_at':retry,'overdue':bool(cfg.get('backup_enabled') and now>due+interval),
            'pending':dict(row) if row else None,'wait_reason':wait,'stops_server':True,'idle_seconds':300}

def enqueue_due(store,enqueue,now=None):
    now=time.time() if now is None else now
    with store.change_lock():
        if store.get('backup_schedule_started_at') is None:store.set('backup_schedule_started_at',now)
        view=status(store,now=now)
        if not view['enabled'] or (view['pending'] and not _future(view['pending'],now)) or now<(view['retry_at'] or view['due_at']):return None
        return enqueue('backup',{'kind':'scheduled'},None,mode='idle_5min')

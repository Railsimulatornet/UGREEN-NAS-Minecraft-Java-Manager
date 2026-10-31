"""Only an admin's explicit automation approval can stage installed-mod updates."""
import json
import time
from . import mods,sources,versions


def stage_updates(store,root,rpc,enqueue):
    cfg=store.get('maintenance')
    if not cfg.get('automatic'):return {'state':'disabled'}
    approval=store.get('automatic_mod_approval') or {};actor=approval.get('actor')
    with store.db() as db:
        user=db.execute('SELECT enabled,admin FROM users WHERE id=?',(actor,)).fetchone()
        jobs=[dict(x) for x in db.execute("SELECT state,payload FROM jobs WHERE kind='apply_mods' AND state IN ('planned','queued','running')")]
    if not user or not user['enabled'] or not user['admin']:return {'state':'approval_unavailable'}
    if any(json.loads(x['payload']).get('automatic') for x in jobs):return {'state':'already_queued'}
    ready=rpc('/maintenance-readiness')
    if not ready.get('ready'):return {'state':'guard_not_ready'}
    with store.change_lock():
        with store.db() as db:rows=[dict(x) for x in db.execute("SELECT * FROM mods WHERE state NOT IN ('superseded','rejected') AND source!='system'")]
        if store.get('pack_pending') or any(x['state']!='installed' or x['enabled']!=x['installed_enabled'] for x in rows):
            return {'state':'manual_changes_pending'}
        available=[x for x in rows if x['available'] and json.loads(x['available']).get('status')=='available' and not (json.loads(x['origin']) if x.get('origin') else {}).get('pack_project')]
        if not available:return {'state':'up_to_date'}
        try:
            for row in available:sources.stage_update(store,root,row['id'])
            with store.db() as db:proposed=mods.proposed_records([dict(x) for x in db.execute("SELECT * FROM mods WHERE state NOT IN ('superseded','rejected')")])
            if {(x['id'],x['enabled']) for x in proposed if x['source']!='system'}=={(x['id'],x['enabled']) for x in rows}:
                return {'state':'up_to_date'}
            report=mods.dependency_report([x for x in proposed if x['enabled']],versions.runtime_components(store,store.get('server')))
            if report['structural_checks']!='passed':raise ValueError('candidate_mod_dependencies_failed')
            identifier=enqueue('apply_mods',{'automatic':True},actor,mode='idle_5min',approved=True)
        except Exception as exc:
            store.event('maintenance','automatic_mod_staging_failed',actor,{'error_class':type(exc).__name__})
            raise
    store.event('maintenance','automatic_mod_maintenance_queued',actor,{'job':identifier,'updates':len(available),'idle_seconds':300})
    try:rpc('/console',{'command':'tellraw @a '+json.dumps({'text':'Mod-Wartung vorgemerkt: erst nach 5 Minuten ohne Spieler. / Mod maintenance queued: only after 5 minutes without players.'})})
    except Exception:pass
    return {'state':'queued','id':identifier,'updates':len(available)}


def cancel_queued(store):
    count=0
    with store.db(immediate=True) as db:
        for row in db.execute("SELECT id,payload FROM jobs WHERE kind='apply_mods' AND state IN ('planned','queued')").fetchall():
            if json.loads(row['payload']).get('automatic') and json.loads(row['payload']).get('automatic_scope')!='folder':
                db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=?",(time.time(),row['id']));count+=1
    return count

def stage_folder_mods(store,root,rpc,enqueue):
    cfg=store.get('maintenance')
    if not cfg.get('folder_automatic',False):return {'state':'disabled'}
    approval=store.get('folder_mod_approval') or {};actor=approval.get('actor')
    with store.db() as db:
        user=db.execute('SELECT enabled,admin FROM users WHERE id=?',(actor,)).fetchone()
        jobs=[json.loads(x[0]) for x in db.execute("SELECT payload FROM jobs WHERE kind='apply_mods' AND state IN ('queued','running')")]
    if not user or not user['enabled'] or not user['admin']:return {'state':'approval_unavailable'}
    if any(x.get('automatic_scope')=='folder' for x in jobs):return {'state':'already_queued'}
    readiness=rpc('/maintenance-readiness')
    if not readiness.get('ready') or readiness.get('visitor_verified') is not True:return {'state':'guard_not_ready'}
    with store.change_lock():
        with store.db() as db:rows=[dict(x) for x in db.execute("SELECT * FROM mods WHERE state NOT IN ('superseded','rejected')")]
        if any(x['state']=='installed' and (x['enabled']!=x['installed_enabled'] or x.get('remove_pending') is not None) for x in rows):return {'state':'manual_changes_pending'}
        approved={v['sha256'] for v in (store.get('manual_imports') or {}).values() if v.get('approval')==approval}
        selected=[x['id'] for x in rows if x['id'] in approved and x['source']=='manual' and x['state']=='staged' and not x.get('replaces')]
        if not selected:return {'state':'up_to_date'}
        proposed=mods.proposed_records(mods.selected_records(rows,selected))
        report=mods.dependency_report([x for x in proposed if x['enabled']],versions.runtime_components(store,store.get('server')))
        if report['structural_checks']!='passed':
            store.event('mods','folder_mod_dependencies_failed',actor,{'files':[x['filename'] for x in rows if x['id'] in selected]})
            return {'state':'dependencies_failed'}
        identifier=enqueue('apply_mods',{'automatic':True,'automatic_scope':'folder','selection':selected,'folder_approval':approval},actor,mode='idle_5min',approved=True)
    store.event('maintenance','folder_mod_maintenance_queued',actor,{'job':identifier,'files':[x['filename'] for x in rows if x['id'] in selected],'idle_seconds':300})
    return {'state':'queued','id':identifier,'mods':len(selected)}

def cancel_folder_queued(store):
    with store.db(immediate=True) as db:
        for row in db.execute("SELECT id,payload FROM jobs WHERE kind='apply_mods' AND state IN ('planned','queued')").fetchall():
            if json.loads(row['payload']).get('automatic_scope')=='folder':db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=?",(time.time(),row['id']))

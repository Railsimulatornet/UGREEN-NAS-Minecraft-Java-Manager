"""Bounded, owner-approved retention without losing pending notifications."""
import hashlib
import json
import secrets
import time
from pydantic import BaseModel,Field,StrictBool,StrictInt

DEFAULT={'enabled':False,'retention_days':30,'delivery_days':30,'interval_hours':24}

class Policy(BaseModel):
    model_config={'extra':'forbid'}
    enabled:StrictBool=False
    retention_days:StrictInt=Field(default=30,ge=1,le=3650)
    delivery_days:StrictInt=Field(default=30,ge=1,le=3650)
    interval_hours:StrictInt=Field(default=24,ge=1,le=168)

class Preview(BaseModel):
    model_config={'extra':'forbid'}
    before:float=Field(gt=0,allow_inf_nan=False)
    category:str=Field(default='',pattern=r'^[a-z_]{0,30}$')

class Delete(BaseModel):
    model_config={'extra':'forbid'}
    token:str=Field(min_length=30,max_length=100)

def policy(store):
    try:return Policy.model_validate(store.get('event_cleanup') or DEFAULT).model_dump()
    except ValueError:return dict(DEFAULT)

def prepare(db):
    # Protect IDs referenced by undelivered messages and events that the dispatch
    # cursor has not processed yet. A temporary table avoids SQLite bind limits.
    db.execute('CREATE TEMP TABLE IF NOT EXISTS protected_event_ids(id INTEGER PRIMARY KEY)')
    db.execute('DELETE FROM protected_event_ids')
    for row in db.execute("SELECT event_ids FROM notification_outbox WHERE state IN ('queued','retry','sending')").fetchall():
        identifiers=json.loads(row['event_ids'])
        db.executemany('INSERT OR IGNORE INTO protected_event_ids VALUES(?)',[(x,) for x in identifiers if type(x) is int])
    maximum=db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]
    row=db.execute("SELECT value FROM settings WHERE name='notification_cursor'").fetchone()
    cursor=json.loads(row['value']) if row else maximum
    if type(cursor) is not int:cursor=0
    return maximum,cursor

def selection(db,before,category='',upper=None):
    maximum,cursor=prepare(db)
    # Keep the maximum ID: INTEGER PRIMARY KEY must never recycle an ID below
    # the notification cursor, even when all older history is removed.
    sql="at<? AND (?='' OR category=?) AND id<=? AND id<=? AND id<>? AND id NOT IN (SELECT id FROM protected_event_ids)"
    return sql,(before,category,category,maximum if upper is None else upper,cursor,maximum)

def signature(db,where,parameters):
    digest=hashlib.sha256();count=0
    for row in db.execute('SELECT id FROM events WHERE '+where+' ORDER BY id',parameters):
        digest.update(str(row['id']).encode()+b'\n');count+=1
    return count,digest.hexdigest()

def preview(store,actor,data):
    now=time.time()
    if data.before>now-60:raise ValueError('event_cleanup_recent')
    raw=secrets.token_urlsafe(32)
    with store.db(immediate=True) as db:
        db.execute("DELETE FROM challenges WHERE kind='event_cleanup' AND expires<=?",(now,))
        upper=db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]
        where,parameters=selection(db,data.before,data.category,upper);count,fingerprint=signature(db,where,parameters)
        context={'before':data.before,'category':data.category,'upper':upper,'count':count,'fingerprint':fingerprint,'generation':actor['generation']}
        db.execute('INSERT INTO challenges(token,user_id,kind,expires,data) VALUES(?,?,?,?,?)',
            (store.digest(raw),actor['id'],'event_cleanup',now+600,json.dumps(context)))
    return {'count':count,'before':data.before,'category':data.category,'token':raw,'expires':now+600}

def delete(store,actor,token):
    now=time.time()
    with store.db(immediate=True) as db:
        row=db.execute("SELECT * FROM challenges WHERE token=? AND user_id=? AND kind='event_cleanup' AND expires>?",(store.digest(token),actor['id'],now)).fetchone()
        if not row:raise ValueError('event_cleanup_preview_expired')
        context=json.loads(row['data'])
        owner=db.execute('SELECT enabled,admin,generation FROM users WHERE id=?',(actor['id'],)).fetchone()
        if not owner or not owner['enabled'] or not owner['admin'] or owner['generation']!=context['generation']:raise ValueError('event_cleanup_preview_expired')
        where,parameters=selection(db,context['before'],context['category'],context['upper'])
        count,fingerprint=signature(db,where,parameters)
        if count!=context['count'] or fingerprint!=context['fingerprint']:raise ValueError('event_cleanup_preview_changed')
        db.execute('DELETE FROM events WHERE '+where,parameters)
        db.execute('DELETE FROM challenges WHERE token=?',(row['token'],))
        db.execute('INSERT INTO events(at,category,event,actor,data) VALUES(?,?,?,?,?)',(now,'audit','events_deleted',actor['id'],json.dumps({'count':count,'before':context['before'],'category':context['category']})))
    return {'deleted':count}

def run_due(store,now=None):
    now=time.time() if now is None else now;cfg=policy(store)
    if not cfg['enabled']:return None
    with store.db(immediate=True) as db:
        saved=db.execute("SELECT value FROM settings WHERE name='event_cleanup'").fetchone()
        cfg=Policy.model_validate(json.loads(saved['value']) if saved else DEFAULT).model_dump()
        if not cfg['enabled']:return None
        row=db.execute("SELECT value FROM settings WHERE name='event_cleanup_approval'").fetchone()
        approval=json.loads(row['value']) if row else {}
        owner=db.execute('SELECT enabled,admin,generation FROM users WHERE id=?',(approval.get('actor'),)).fetchone()
        if not owner or not owner['enabled'] or not owner['admin'] or owner['generation']!=approval.get('generation'):return None
        row=db.execute("SELECT value FROM settings WHERE name='event_cleanup_last'").fetchone()
        previous=json.loads(row['value']) if row else {'at':approval.get('at',now)}
        if now-previous.get('at',now)<cfg['interval_hours']*3600:return None
        where,parameters=selection(db,now-cfg['retention_days']*86400)
        deleted=db.execute('DELETE FROM events WHERE '+where,parameters).rowcount
        deliveries=db.execute("DELETE FROM notification_outbox WHERE created<? AND state NOT IN ('queued','retry','sending')",(now-cfg['delivery_days']*86400,)).rowcount
        result={'at':now,'events_deleted':deleted,'deliveries_deleted':deliveries}
        db.execute('INSERT INTO settings VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',('event_cleanup_last',json.dumps(result)))
        if deleted or deliveries:db.execute('INSERT INTO events(at,category,event,actor,data) VALUES(?,?,?,?,?)',(now,'audit','history_cleaned',approval['actor'],json.dumps(result)))
    return result

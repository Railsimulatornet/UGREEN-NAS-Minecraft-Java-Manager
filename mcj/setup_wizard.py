"""Guided review of a new installation; never an access or security approval."""
import time
from pydantic import BaseModel,ConfigDict,Field

class Progress(BaseModel):
    model_config=ConfigDict(extra='forbid')
    step:int=Field(ge=0,le=4,strict=True)
    complete:bool=Field(default=False,strict=True)
    reviewed:bool=Field(default=False,strict=True)

def saved(st):
    value=st.get('setup_wizard') or {}
    return value if isinstance(value,dict) else {}

def pending(st):
    value=saved(st)
    return value.get('enabled') is True and not value.get('completed')

def status(st,address):
    value=saved(st);server=st.get('server');maintenance=st.get('maintenance');smtp=st.get('smtp')
    step=value.get('step',0)
    with st.db() as db:
        backup_count=db.execute("SELECT COUNT(*) FROM backups WHERE state='verified'").fetchone()[0]
    return {'step':step if type(step) is int and 0<=step<=4 else 0,
            'pending':pending(st),'completed':bool(value.get('completed')),
            'server':{key:server.get(key) for key in ['version','java','loader','loader_version','memory_mb','container_memory_mb']},
            'web_address':address,'backups':{'enabled':bool(maintenance.get('backup_enabled')),
                'interval_minutes':maintenance.get('backup_minutes'),'retention_days':maintenance.get('retention_days'),
                'verified_count':backup_count},
            'mail_configured':bool(smtp.get('host') and smtp.get('sender') and smtp.get('password'))}

def advance(st,data,actor):
    if data.complete and (data.step!=4 or not data.reviewed):raise ValueError('setup_review_required')
    with st.change_lock():
        old=saved(st)
        value={'enabled':old.get('enabled') is True,'step':data.step,
               'completed':bool(old.get('completed') or data.complete),'updated':time.time()}
        if old.get('completed_at'):value['completed_at']=old['completed_at']
        elif data.complete:value['completed_at']=time.time()
        st.set('setup_wizard',value)
    if data.complete and not old.get('completed'):
        st.event('settings','setup_wizard_completed',actor,{'reviewed':True})


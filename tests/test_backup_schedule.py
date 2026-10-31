import json,time,secrets
import pytest
from mcj.backup_schedule import status,enqueue_due
from test_automatic import prepare

def test_a_due_backup_waits_without_claiming_success_or_creating_duplicates(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);st.set('backup_schedule_started_at',1000)
    assert enqueue_due(st,enqueue,now=2000) is None
    identifier=enqueue_due(st,enqueue,now=3000);assert identifier and len(calls)==1
    for now in (10000,20000,30000):assert enqueue_due(st,enqueue,now=now) is None
    view=status(st,{'players_online':3},now=5000)
    assert view['last_success'] is None and view['age_seconds'] is None and view['overdue']
    assert view['pending']['id']==identifier and view['wait_reason']=='players_online' and view['stops_server']
    assert status(st,{},now=5000)['wait_reason']=='status_unknown'
    assert status(st,{'players_online':0},now=5000)['wait_reason']=='continuous_idle'

def test_manager_restart_keeps_due_time_and_single_pending_backup(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);st.set('backup_schedule_started_at',1000)
    enqueue_due(st,enqueue,now=3000)
    before=status(st,now=5000)
    from mcj.store import Store
    reopened=Store(st.state,tmp_path/'key')
    assert status(reopened,now=6000)['due_at']==before['due_at']
    assert enqueue_due(reopened,enqueue,now=10000) is None and len(calls)==1

def test_failed_attempt_has_bounded_retry_but_never_resets_success_age(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);st.set('backup_schedule_started_at',1000)
    with st.db() as db:
        db.execute("INSERT INTO backups(id,created,kind,state) VALUES('old',1000,'manual','verified')")
        db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",('x','backup','failed',4000,4000,1,'idle_5min','{}','{}',1))
    view=status(st,now=4500)
    assert view['last_success']==1000 and view['age_seconds']==3500 and view['retry_at']==5800
    assert enqueue_due(st,enqueue,now=4500) is None and not calls

def test_a_historical_success_does_not_claim_a_missing_archive_is_available(tmp_path):
    st,_,_,_,_=prepare(tmp_path)
    with st.db() as db:db.execute("INSERT INTO backups(id,created,kind,state,path) VALUES('old',1000,'manual','verified','20261028T000000Z-12345678.tar.gz')")
    view=status(st,now=4500,backup_root=tmp_path/'missing')
    assert view['last_success']==1000 and view['last_archive_available'] is False

@pytest.mark.parametrize('server',[{}, {'players_online':0}, {'players_online':3}])
def test_a_future_backup_reports_its_actual_schedule_before_player_conditions(tmp_path,server):
    st,_,_,enqueue,_=prepare(tmp_path)
    identifier=enqueue('backup',{'kind':'manual','_scheduled_at':6000},None,mode='scheduled')
    view=status(st,server,now=5000)
    assert view['wait_reason']=='scheduled'
    assert view['pending']['id']==identifier and view['pending']['scheduled_at']==6000
    assert 'payload' not in view['pending']

@pytest.mark.parametrize('server,expected',[({},'status_unknown'),({'players_online':3},'players_online'),({'players_online':0},'queued')])
def test_a_due_scheduled_backup_reports_the_remaining_start_condition(tmp_path,server,expected):
    st,_,_,enqueue,_=prepare(tmp_path)
    enqueue('backup',{'kind':'manual','_scheduled_at':5000},None,mode='scheduled')
    assert status(st,server,now=5000)['wait_reason']==expected

def test_a_running_backup_does_not_still_claim_it_is_waiting_for_its_schedule(tmp_path):
    st,_,_,enqueue,_=prepare(tmp_path)
    identifier=enqueue('backup',{'kind':'manual','_scheduled_at':6000},None,mode='scheduled')
    with st.db() as db:db.execute("UPDATE jobs SET state='running' WHERE id=?",(identifier,))
    assert status(st,{},now=5000)['wait_reason']=='running'

def test_cancelling_a_future_request_does_not_postpone_the_automatic_backup(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);st.set('backup_schedule_started_at',1000)
    identifier=enqueue('backup',{'kind':'manual','_scheduled_at':20000},None,mode='scheduled')
    with st.db() as db:db.execute("UPDATE jobs SET state='cancelled',created=2500,updated=2600 WHERE id=?",(identifier,))
    assert status(st,now=3000)['retry_at']==2800
    assert enqueue_due(st,enqueue,now=3000) and len(calls)==2

def test_a_future_manual_backup_does_not_suppress_due_automatic_protection(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);st.set('backup_schedule_started_at',1000)
    future=enqueue('backup',{'kind':'manual','_scheduled_at':20000},None,mode='scheduled')
    automatic=enqueue_due(st,enqueue,now=3000)
    assert automatic and automatic!=future and len(calls)==2
    for now in (3100,5000,10000):assert enqueue_due(st,enqueue,now=now) is None
    view=status(st,{'players_online':0},now=3000)
    assert view['pending']['id']==automatic and view['wait_reason']=='continuous_idle'
    with st.db() as db:assert db.execute('SELECT state FROM jobs WHERE id=?',(future,)).fetchone()[0]=='queued'

def test_a_running_backup_takes_display_priority_over_an_older_future_request(tmp_path):
    st,_,_,enqueue,_=prepare(tmp_path)
    enqueue('backup',{'kind':'manual','_scheduled_at':20000},None,mode='scheduled')
    running=enqueue('backup',{'kind':'scheduled'},None,mode='idle_5min')
    with st.db() as db:db.execute("UPDATE jobs SET state='running' WHERE id=?",(running,))
    view=status(st,{},now=3000)
    assert view['pending']['id']==running and view['wait_reason']=='running'

def test_retry_delay_starts_when_a_failed_attempt_ends_not_when_it_started(tmp_path):
    st,_,calls,enqueue,_=prepare(tmp_path);st.set('backup_schedule_started_at',1000)
    with st.db() as db:db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",('long','backup','failed',1000,4000,1,'idle_5min','{}','{}',1))
    assert status(st,now=4500)['retry_at']==5800
    assert enqueue_due(st,enqueue,now=4500) is None and not calls

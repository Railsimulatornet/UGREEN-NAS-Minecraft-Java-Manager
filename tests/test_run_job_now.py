import json,time
from test_security import environment,enroll,post

def job(st,identifier='a'*32,state='planned',mode='scheduled',actor=None):
    with st.db() as db:
        db.execute('INSERT INTO jobs(id,kind,state,created,updated,actor,mode,payload,approved) VALUES(?,?,?,?,?,?,?,?,?)',
            (identifier,'source_check',state,time.time(),time.time(),actor,mode,json.dumps({'automatic':True,'_scheduled_at':time.time()+3600}),0))
        return dict(db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone())

def test_run_now_updates_existing_job_and_removes_schedule_once(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;job(st)
    path='/api/jobs/'+'a'*32+'/run-now'
    assert post(client,path,{'confirmation':'run_now'}).status_code==403
    assert post(client,path,{'confirmation':'yes'},csrf).status_code==422
    assert post(client,path,{'confirmation':'run_now'},csrf).status_code==200
    with st.db() as db:
        row=dict(db.execute('SELECT * FROM jobs').fetchone());assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==1
    assert row['mode']=='immediate' and row['actor']==1 and row['approved']==1 and row['state']=='queued'
    assert json.loads(row['payload'])=={'automatic':False}
    assert post(client,path,{'confirmation':'run_now'},csrf).status_code==409

def test_force_rejects_running_finished_and_non_admin(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;job(st)
    path='/api/jobs/'+'a'*32+'/run-now';job(st,'b'*32,'running')
    assert post(client,path,{'confirmation':'run_now'},csrf).json()['detail']=='maintenance_busy'
    with st.db() as db:db.execute("UPDATE jobs SET state='succeeded'")
    assert post(client,path,{'confirmation':'run_now'},csrf).status_code==409
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,path,{'confirmation':'run_now'},csrf).status_code==403

def test_executor_reads_current_row_and_preserves_cancelled_job(environment,monkeypatch):
    from mcj import sources
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    stale=job(st,actor=999);seen=[]
    monkeypatch.setattr(sources,'check_source',lambda *args:seen.append(args) or {'ok':True})
    with st.db() as db:db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps({'id':'fixture-source'}),stale['id']))
    assert post(client,'/api/jobs/'+stale['id']+'/run-now',{'confirmation':'run_now'},csrf).status_code==200
    app.state.execute_job(stale)
    with st.db() as db:row=db.execute('SELECT state,result FROM jobs WHERE id=?',(stale['id'],)).fetchone()
    assert row['state']=='succeeded',row['result'];assert seen
    cancelled=job(st,'c'*32)
    with st.db() as db:db.execute("UPDATE jobs SET state='cancelled' WHERE id=?",(cancelled['id'],))
    app.state.execute_job(cancelled)
    with st.db() as db:assert db.execute('SELECT state FROM jobs WHERE id=?',(cancelled['id'],)).fetchone()[0]=='cancelled'

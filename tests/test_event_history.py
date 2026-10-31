import json,time
import pytest
from mcj import event_history,dispatch
from test_security import environment,enroll,post

@pytest.mark.parametrize('suffix',['','?category=auth','?after=0&category=email'])
def test_global_event_history_requires_verified_administrator(environment,suffix):
    app,client,_,_=environment;st=app.state.store
    path='/api/events'+suffix
    assert client.get(path).status_code==401
    enroll(environment)
    st.event('email','smtp_accepted',2,{'recipient':'other@example.invalid'})
    st.event('auth','password_verified',2,{'ip':'203.0.113.8'})
    response=client.get(path)
    assert response.status_code==200
    assert any(x['actor']==2 for x in response.json())
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    response=client.get(path)
    assert response.status_code==403 and response.json()['detail']=='admin_required'
    assert 'other@example.invalid' not in response.text and '203.0.113.8' not in response.text
    assert client.get('/api/auth/me').status_code==200


def seed(st):
    with st.db() as db:
        ids=[]
        for category in ['server','server','auth']:
            ids.append(db.execute('INSERT INTO events(at,category,event,data) VALUES(?,?,?,?)',(time.time()-100*86400,category,'old_fixture','{}')).lastrowid)
        latest=db.execute('INSERT INTO events(at,category,event,data) VALUES(?,?,?,?)',(time.time(),'system','recent_fixture','{}')).lastrowid
    st.set('notification_cursor',latest)
    return ids,latest

def test_preview_confirm_is_owner_bound_single_use_and_preserves_pending_events(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;ids,latest=seed(st)
    with st.db() as db:db.execute('INSERT INTO notification_outbox(channel,user_id,created,event_ids,state) VALUES(?,?,?,?,?)',('email',1,time.time()-90*86400,json.dumps([ids[0]]),'queued'))
    before=time.time()-30*86400
    assert post(client,'/api/events/cleanup-preview',{'before':before}).status_code==403
    preview=post(client,'/api/events/cleanup-preview',{'before':before,'category':'server'},csrf).json()
    assert preview['count']==1
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM events WHERE event=?',('old_fixture',)).fetchone()[0]==3
    result=post(client,'/api/events/cleanup',{'token':preview['token']},csrf)
    assert result.status_code==200 and result.json()['deleted']==1
    assert post(client,'/api/events/cleanup',{'token':preview['token']},csrf).status_code==409
    with st.db() as db:
        assert db.execute('SELECT 1 FROM events WHERE id=?',(ids[0],)).fetchone()
        assert db.execute('SELECT 1 FROM events WHERE id=?',(ids[2],)).fetchone()
        assert db.execute('SELECT 1 FROM events WHERE id=?',(latest,)).fetchone()
    assert 'events_deleted' in client.get('/api/events/export').text

def test_changed_protected_set_requires_new_preview(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;ids,_=seed(st)
    preview=post(client,'/api/events/cleanup-preview',{'before':time.time()-86400},csrf).json()
    with st.db() as db:db.execute('INSERT INTO notification_outbox(channel,user_id,created,event_ids,state) VALUES(?,?,?,?,?)',('email',1,time.time(),json.dumps([ids[0]]),'sending'))
    assert post(client,'/api/events/cleanup',{'token':preview['token']},csrf).json()['detail']=='event_cleanup_preview_changed'
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM events WHERE event=?',('old_fixture',)).fetchone()[0]==3

def test_automatic_retention_is_opt_in_interval_bound_and_preserves_event_id_cursor(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;ids,latest=seed(st);now=time.time()
    assert event_history.run_due(st,now+86400) is None
    with st.db() as db:
        for state in ['queued','sending','smtp_accepted','failed','delivery_uncertain']:
            db.execute('INSERT INTO notification_outbox(channel,user_id,created,event_ids,state) VALUES(?,?,?,?,?)',('email',1,now-90*86400,json.dumps([ids[0]]),state))
    cfg={'enabled':True,'retention_days':30,'delivery_days':30,'interval_hours':24}
    assert post(client,'/api/events/cleanup-policy',cfg,csrf).status_code==200
    assert event_history.run_due(st,now+100) is None
    result=event_history.run_due(st,now+86401)
    assert result['events_deleted']==2 and result['deliveries_deleted']==3
    assert event_history.run_due(st,now+86402) is None
    with st.db() as db:
        assert {x[0] for x in db.execute('SELECT state FROM notification_outbox')}=={'queued','sending'}
        assert db.execute('SELECT 1 FROM events WHERE id=?',(ids[0],)).fetchone()
        assert db.execute('SELECT 1 FROM events WHERE id=?',(latest,)).fetchone()
        maximum=db.execute('SELECT MAX(id) FROM events').fetchone()[0]
    st.event('server','new_fixture');dispatch.queue_events(st)
    with st.db() as db:assert db.execute('SELECT MAX(id) FROM events').fetchone()[0]>maximum

def test_disable_policy_and_demote_owner_stop_automatic_cleanup(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;seed(st);now=time.time()
    cfg={'enabled':True,'retention_days':1,'delivery_days':1,'interval_hours':1}
    post(client,'/api/events/cleanup-policy',cfg,csrf)
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert event_history.run_due(st,now+7200) is None
    with st.db() as db:db.execute('UPDATE users SET admin=1 WHERE id=1')
    cfg['enabled']=False;assert post(client,'/api/events/cleanup-policy',cfg,csrf).status_code==200
    assert event_history.run_due(st,now+7200) is None
    with st.db() as db:assert db.execute('SELECT COUNT(*) FROM events WHERE event=?',('old_fixture',)).fetchone()[0]==3

@pytest.mark.parametrize('value',[{'enabled':True,'retention_days':0},{'enabled':True,'retention_days':True},{'interval_hours':0},{'interval_hours':169},{'delivery_days':3651},{'enabled':True,'user_id':2}])
def test_retention_schema_and_access_controls(environment,value):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    assert post(client,'/api/events/cleanup-policy',value,csrf).status_code==422
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/events/cleanup-policy').status_code==403
    assert post(client,'/api/events/cleanup-preview',{'before':time.time()-86400},csrf).status_code==403

def test_expired_preview_and_undispatched_events_are_not_deleted(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;ids,_=seed(st);st.set('notification_cursor',ids[0])
    preview=post(client,'/api/events/cleanup-preview',{'before':time.time()-86400},csrf).json();assert preview['count']==1
    with st.db() as db:db.execute("UPDATE challenges SET expires=0 WHERE kind='event_cleanup'")
    assert post(client,'/api/events/cleanup',{'token':preview['token']},csrf).status_code==409
    assert post(client,'/api/events/cleanup-preview',{'before':'Infinity'},csrf).status_code==422

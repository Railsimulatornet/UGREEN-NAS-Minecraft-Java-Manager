import json,time
import pytest
from fastapi.testclient import TestClient
from test_security import environment,enroll,post
from mcj import auth


def test_delete_revokes_credentials_pending_jobs_and_links_preserves_audit(environment):
 app,client,creds,mail=environment;csrf=enroll(environment)['csrf'];st=app.state.store
 with st.db() as db:target=dict(db.execute("SELECT * FROM users WHERE username='Moritz'").fetchone())
 other=TestClient(app,base_url='https://testserver');response=other.post('/api/auth/login',json={'username':'Moritz','password':creds['Moritz']['password']},headers={'Origin':'https://testserver'});assert response.status_code==200
 with st.db() as db:
  db.execute("INSERT INTO challenges(token,user_id,kind,expires) VALUES('fixture',?,'reset',?)",(target['id'],time.time()+600))
  db.execute("INSERT INTO recovery_codes(user_id,hash) VALUES(?,'fixture')",(target['id'],))
  db.execute("INSERT INTO jobs(id,kind,state,created,updated,actor,mode,payload) VALUES('fixture','backup','queued',?,?,?,'manual','{}')",(time.time(),time.time(),target['id']))
  db.execute("INSERT INTO client_packs(id,number,created,actor,fingerprint,sha256,size,manifest) VALUES('fixture',1,?,?,'fixture','fixture',1,'{}')",(time.time(),target['id']))
  db.execute("INSERT INTO client_pack_links(id,pack_id,actor,created,expires,token_hash) VALUES('fixture','fixture',?,?,?,'fixture')",(target['id'],time.time(),time.time()+600))
  db.execute("INSERT INTO notification_outbox(channel,user_id,created,event_ids) VALUES('email',?,?,'[]')",(target['id'],time.time()))
 st.event('user','fixture_history',target['id']);st.set('admin_session_policy:'+str(target['id']),{'fixture':True})
 assert post(client,f"/api/users/{target['id']}/delete",{'confirmation':'Wrong'},csrf).status_code==409
 assert other.get('/api/auth/me').status_code==200
 result=post(client,f"/api/users/{target['id']}/delete",{'confirmation':'Moritz'},csrf);assert result.status_code==200,result.text
 assert other.get('/api/auth/me').status_code==401
 assert other.post('/api/auth/login',json={'username':'Moritz','password':creds['Moritz']['password']},headers={'Origin':'https://testserver'}).status_code==401
 assert len(client.get('/api/users').json())==1
 with st.db() as db:
  row=dict(db.execute('SELECT * FROM users WHERE id=?',(target['id'],)).fetchone());assert row['deleted_at'] and not row['enabled'] and not row['admin'] and row['password']=='' and row['totp'] is None and row['notifications']=='{}'
  for table in ['sessions','challenges','recovery_codes']:assert db.execute('SELECT COUNT(*) FROM '+table+' WHERE user_id=?',(target['id'],)).fetchone()[0]==0
  assert db.execute("SELECT state FROM jobs WHERE id='fixture'").fetchone()[0]=='cancelled'
  assert db.execute("SELECT revoked FROM client_pack_links WHERE id='fixture'").fetchone()[0]
  assert db.execute("SELECT state FROM notification_outbox").fetchone()[0]=='cancelled'
  assert db.execute("SELECT COUNT(*) FROM events WHERE event='fixture_history'").fetchone()[0]==1
  assert db.execute("SELECT COUNT(*) FROM events WHERE event='user_deleted'").fetchone()[0]==1
 assert st.get('admin_session_policy:'+str(target['id'])) is None
 assert post(client,f"/api/users/{target['id']}/delete",{'confirmation':'Moritz'},csrf).status_code==404
 assert post(client,f"/api/users/{target['id']}",{'username':'Moritz','email':'moritz@example.invalid','enabled':True,'admin':True},csrf).status_code==404
 recreated=post(client,'/api/users',{'username':'Moritz','email':'moritz@example.invalid'},csrf);assert recreated.status_code==200 and recreated.json()['id']!=target['id']


@pytest.mark.parametrize('block',['running','sending'])
def test_active_user_operation_blocks_delete_atomically(environment,block):
 app,client,creds,mail=environment;csrf=enroll(environment)['csrf'];st=app.state.store
 with st.db() as db:
  uid=db.execute("SELECT id FROM users WHERE username='Moritz'").fetchone()[0]
  if block=='running':db.execute("INSERT INTO jobs(id,kind,state,created,updated,actor,mode,payload) VALUES('fixture','backup','running',?,?,?,'manual','{}')",(time.time(),time.time(),uid))
  else:db.execute("INSERT INTO notification_outbox(channel,user_id,created,event_ids,state) VALUES('email',?,?,'[]','sending')",(uid,time.time()))
 response=post(client,f'/api/users/{uid}/delete',{'confirmation':'Moritz'},csrf);assert response.status_code==409
 with st.db() as db:assert db.execute('SELECT deleted_at FROM users WHERE id=?',(uid,)).fetchone()[0] is None


def test_user_delete_requires_full_admin_and_csrf_and_protects_self(environment):
 app,client,creds,mail=environment
 assert post(client,'/api/users/2/delete',{'confirmation':'Moritz'}).status_code==403
 csrf=enroll(environment)['csrf']
 assert post(client,'/api/users/2/delete',{'confirmation':'Moritz'}).status_code==403
 assert post(client,'/api/users/1/delete',{'confirmation':'Roman'},csrf).status_code==409
 with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
 assert post(client,'/api/users/2/delete',{'confirmation':'Moritz'},csrf).status_code==403

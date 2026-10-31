import json
import pytest
from cryptography.fernet import Fernet
from mcj import dispatch,notify
from mcj.store import Store
from mcj.notification_policy import visible_to,account_subject
from test_security import environment,enroll,post

@pytest.fixture
def configured(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    st=Store(tmp_path/'state',key,initial_accounts=[{'username':'Owner','email':'owner@example.invalid'},{'username':'Viewer','email':'viewer@example.invalid'}])
    with st.db() as db:
        owner=db.execute("SELECT id FROM users WHERE username='Owner'").fetchone()[0]
        viewer=db.execute("SELECT id FROM users WHERE username='Viewer'").fetchone()[0]
        db.execute('UPDATE users SET admin=0,notifications=? WHERE id=?',(json.dumps({'enabled':True,'categories':['auth','user','audit','server']}),viewer))
    dispatch.queue_events(st)
    return st,owner,viewer

def test_nonadmin_receives_own_account_and_shared_status_but_no_foreign_security_events(configured,monkeypatch):
    st,owner,viewer=configured
    foreign=st.event('auth','password_reset_requested',owner)
    own=st.event('auth','login_success',viewer)
    shared=st.event('server','server_start',owner)
    target=st.event('user','user_updated',owner,{'id':viewer})
    audit=st.event('audit','diagnostics_downloaded',owner)
    dispatch.queue_events(st)
    with st.db() as db:
        row=db.execute('SELECT event_ids FROM notification_outbox WHERE user_id=?',(viewer,)).fetchone()
        selected=json.loads(row[0])
    # Event IDs are read from persisted events, not inferred from the return value of event().
    with st.db() as db:events=[dict(x) for x in db.execute('SELECT * FROM events')]
    actual=[x for x in events if x['id'] in selected]
    assert {x['event'] for x in actual}=={'login_success','server_start','user_updated'}
    sent=[]
    monkeypatch.setattr(notify,'send_email',lambda s,to,subject,body,actor=None:sent.append((to,body)) or {'status':'smtp_accepted'})
    assert dispatch.dispatch_one(st,'https://manager.invalid')
    assert sent[0][0]=='viewer@example.invalid' and 'Owner' not in sent[0][1] and 'Viewer' in sent[0][1]

def test_demotion_filters_an_existing_admin_outbox_again_at_delivery(configured,monkeypatch):
    st,owner,viewer=configured
    with st.db() as db:db.execute('UPDATE users SET admin=1 WHERE id=?',(viewer,))
    st.event('auth','password_changed',owner);st.event('auth','login_success',viewer)
    dispatch.queue_events(st)
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=?',(viewer,))
    sent=[]
    monkeypatch.setattr(notify,'send_email',lambda s,to,subject,body,actor=None:sent.append(body) or {'status':'smtp_accepted'})
    assert dispatch.dispatch_one(st,'https://manager.invalid')
    assert len(sent)==1 and 'Viewer' in sent[0] and 'Owner' not in sent[0]

def test_target_account_is_separate_from_initiating_admin_and_invalid_subject_fails_closed():
    viewer={'id':2,'admin':0,'enabled':1}
    event={'category':'auth','event':'factor_recovery_completed','actor':1,'data':json.dumps({'id':2})}
    assert account_subject(event)==2 and visible_to(viewer,event)
    assert not visible_to({**viewer,'id':1},event)
    for data in ['broken',json.dumps({'id':True}),json.dumps({'id':'2'}),json.dumps({})]:
        assert not visible_to(viewer,{**event,'data':data})
    assert not visible_to(viewer,{'category':'audit','actor':2})
    assert visible_to({**viewer,'admin':1},{'category':'audit','actor':1})

def test_choosing_all_profile_categories_does_not_grant_global_event_authority(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,'/api/profile',{'language':'en','notifications':{'enabled':True,'categories':['auth','user','audit']}},csrf).status_code==200
    dispatch.queue_events(st);st.event('auth','password_reset_requested',2);dispatch.queue_events(st)
    monkeypatch.setattr(notify,'send_email',lambda *args,**kwargs:pytest.fail('Other account event escaped the recipient boundary'))
    assert dispatch.dispatch_one(st,'https://manager.invalid') is False

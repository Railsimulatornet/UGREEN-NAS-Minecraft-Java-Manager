import json
import pytest
from cryptography.fernet import Fernet
from mcj.store import Store
from mcj import dispatch,notify

@pytest.fixture
def store(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    return Store(tmp_path/'state',key,initial_accounts=[{'username':'Roman','email':'roman@example.invalid'},{'username':'Moritz','email':'moritz@example.invalid'}])

def preferences(store,name,language,categories):
    with store.db() as db:db.execute('UPDATE users SET language=?,notifications=? WHERE username=?',
        (language,json.dumps({'enabled':True,'categories':categories}),name))

def test_event_to_persisted_queue_to_language_filtered_delivery(store,monkeypatch):
    preferences(store,'Roman','de',['backup']);preferences(store,'Moritz','en',['maintenance'])
    dispatch.queue_events(store)
    store.event('server','server_start');store.event('backup','backup_verified');store.event('maintenance','mods_applied')
    dispatch.queue_events(store);dispatch.queue_events(store)
    deliveries=[]
    def send(st,recipient,subject,body,actor=None):
        deliveries.append((recipient,subject,body));st.event('email','smtp_accepted');return {'status':'smtp_accepted'}
    monkeypatch.setattr(notify,'send_email',send)
    while dispatch.dispatch_one(store,'https://manager.invalid'):pass
    dispatch.queue_events(store)
    assert len(deliveries)==2
    assert deliveries[0][0]=='roman@example.invalid' and 'Backup erstellt und geprüft' in deliveries[0][2]
    assert 'Mods applied' in deliveries[1][2] and 'Backup erstellt' not in deliveries[1][2]
    with store.db() as db:assert [x[0] for x in db.execute('SELECT state FROM notification_outbox')]==['smtp_accepted','smtp_accepted']

def test_delivery_failures_are_bounded_and_secrets_not_logged(store,monkeypatch):
    preferences(store,'Roman','de',['system','backup']);dispatch.queue_events(store)
    store.event('backup','backup_failed');dispatch.queue_events(store)
    def failed(*args,**kwargs):raise RuntimeError('unlogged-sensitive-provider-value')
    monkeypatch.setattr(notify,'send_email',failed)
    for _ in range(3):
        assert dispatch.dispatch_one(store,'https://manager.invalid')
        dispatch.queue_events(store)
        with store.db() as db:db.execute('UPDATE notification_outbox SET next_at=0')
    with store.db() as db:
        rows=[dict(x) for x in db.execute('SELECT * FROM notification_outbox')]
        events=[x[0] for x in db.execute('SELECT data FROM events')]
    assert len(rows)==1 and rows[0]['attempts']==3 and rows[0]['state']=='failed'
    assert 'unlogged-sensitive-provider-value' not in json.dumps(events)

def test_disable_before_delivery_and_interrupted_send(store,monkeypatch):
    preferences(store,'Roman','de',['backup']);dispatch.queue_events(store)
    store.event('backup','backup_verified');dispatch.queue_events(store)
    with store.db() as db:db.execute("UPDATE users SET enabled=0 WHERE username='Roman'")
    monkeypatch.setattr(notify,'send_email',lambda *args,**kwargs:pytest.fail('Disabled account received a message'))
    assert dispatch.dispatch_one(store,'https://manager.invalid')
    with store.db() as db:
        assert db.execute('SELECT state FROM notification_outbox').fetchone()[0]=='cancelled'
        db.execute("UPDATE notification_outbox SET state='sending'")
    dispatch.recover_inflight(store)
    with store.db() as db:assert db.execute('SELECT state FROM notification_outbox').fetchone()[0]=='delivery_uncertain'

def test_discord_status_edits_existing_message_and_recreates_deleted_message(store,monkeypatch):
    import httpx
    cfg=store.get('discord');cfg.update(enabled=True,webhook='https://discord.com/api/webhooks/123/test-token',events=['status'])
    store.set('discord',cfg,True)
    methods=[]
    class Client:
        deleted=False
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,json):
            methods.append('POST');assert json['allowed_mentions']=={'parse':[]}
            return httpx.Response(200,json={'id':'456'},request=httpx.Request('POST','https://discord.com/'))
        def patch(self,url,json):
            methods.append('PATCH')
            return httpx.Response(404 if self.deleted else 200,json={},request=httpx.Request('PATCH','https://discord.com/'))
    monkeypatch.setattr(notify.httpx,'Client',Client)
    notify.send_discord(store,'online',status=True);notify.send_discord(store,'online again',status=True)
    assert methods==['POST','PATCH'] and store.get('discord')['status_message_id']=='456'
    Client.deleted=True;notify.send_discord(store,'online',status=True)
    assert methods==['POST','PATCH','PATCH','POST']
    with store.db() as db:assert 'test-token' not in db.execute("SELECT value FROM settings WHERE name='discord'").fetchone()[0]

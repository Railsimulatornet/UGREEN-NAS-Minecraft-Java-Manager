import json
from cryptography.fernet import Fernet
from mcj.store import Store
from mcj.player_events import read_batch,ingest

def test_connected_journal_retry_and_session_duration(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    store=Store(tmp_path/'state',key)
    path=tmp_path/'events.jsonl'
    def record(event,at):return {'event':event,'at':at,'name':'Acceptance','uuid':'00000000-0000-0000-0000-000000000001'}
    first=json.dumps(record('player_login',1000)).encode()+b'\n'
    second=json.dumps(record('player_logout',1123)).encode()+b'\n'
    path.write_bytes(first+second[:-2])
    batch=read_batch(path,{})
    assert len(batch['records'])==1 and batch['cursor']['offset']==len(first)
    ingest(store,batch);ingest(store,batch)
    path.write_bytes(first+second)
    next_batch=read_batch(path,store.get('guard_event_cursor'));ingest(store,next_batch)
    with store.db() as db:rows=[dict(x) for x in db.execute("SELECT * FROM events WHERE category='player'")]
    assert len(rows)==2 and rows[0]['at']==1000 and rows[1]['at']==1123
    assert json.loads(rows[1]['data'])['session_seconds']==123
    assert read_batch(path,store.get('guard_event_cursor'))['records']==[]


def test_moderation_audit_does_not_break_login_session_duration(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());store=Store(tmp_path/'state',key)
    identifier='00000000-0000-0000-0000-000000000001'
    def record(event,at,**fields):return {'uuid':identifier,'name':'Acceptance','event':event,'at':at,**fields}
    path=tmp_path/'events.jsonl';values=[record('player_login',1000),
        record('player_moderation',1050,action='announce',detail='Grüße',phase='authorized'),record('player_logout',1123)]
    path.write_text(''.join(json.dumps(x)+'\n' for x in values))
    batch=read_batch(path,{});assert len(batch['records'])==3;ingest(store,batch)
    with store.db() as db:
        rows=[dict(x) for x in db.execute("SELECT * FROM events WHERE category='player' ORDER BY id")]
    assert json.loads(rows[1]['data'])['phase']=='authorized'
    assert json.loads(rows[-1]['data'])['session_seconds']==123
    malformed=record('player_moderation',1150,action='op',detail='no',phase='authorized')
    path.write_text(json.dumps(malformed)+'\n')
    assert read_batch(path,{})['records']==[]

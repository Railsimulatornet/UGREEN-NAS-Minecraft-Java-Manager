from contextlib import contextmanager
import sqlite3,time
from test_security import environment,enroll
from mcj import player_presence

IDENTIFIER='be4f2732-2e31-4b8d-9752-1c51a0abc02c'

def report():return {'source':'minecraft_rcon','checked_at':time.time(),'online_names':['FixturePlayer'],'players':[{'uuid':IDENTIFIER,'name':'FixturePlayer','first_seen':None,'last_seen':time.time(),'online_since':time.time()-60,'play_seconds':120}]}

def test_valid_presence_not_discarded_for_missing_first_seen(environment):
    app,client,_,_=environment;enroll(environment);app.state.rpc=lambda path:report()
    result=client.get('/api/players');assert result.status_code==200
    data=result.json();assert data['source']=='minecraft_rcon' and data['players'][0]['online'] is True
    assert data['players'][0]['first_seen']>0

def test_history_write_failure_does_not_turn_online_players_into_unknown(environment,monkeypatch):
    app,client,_,_=environment;enroll(environment);st=app.state.store
    with st.db() as db:db.execute('INSERT INTO players(uuid,name,first_seen) VALUES(?,?,?)',(IDENTIFIER,'FixturePlayer',time.time()-100))
    original=st.db
    class FailHistoryWrite:
        def __init__(self,connection):self.connection=connection
        def execute(self,sql,*args):
            if sql.startswith('INSERT INTO players'):raise sqlite3.OperationalError('fixture locked')
            return self.connection.execute(sql,*args)
        def __getattr__(self,name):return getattr(self.connection,name)
    @contextmanager
    def database(*args,**kwargs):
        with original(*args,**kwargs) as connection:yield FailHistoryWrite(connection)
    monkeypatch.setattr(st,'db',database);app.state.rpc=lambda path:report()
    data=client.get('/api/players').json()
    assert data['source']=='minecraft_rcon' and data['history_update_pending']
    assert data['players'][0]['online'] is True
    app.state.rpc=lambda path:(_ for _ in ()).throw(RuntimeError('fixture unavailable'))
    data=client.get('/api/players').json();assert data['players'][0]['online'] is None

def test_short_read_only_transport_failure_is_retried_with_a_fresh_snapshot():
    calls=[]
    def load(command):
        calls.append(command)
        if len(calls)==1:raise TimeoutError('fixture timeout')
        return 'There are 1 of a max of 20 players online: FixturePlayer'
    assert player_presence.query(load)==(['FixturePlayer'],None,2) and calls==['list','list']
    calls.clear()
    def rejected(command):calls.append(command);raise RuntimeError('RCON authentication rejected')
    assert player_presence.query(rejected)==(None,'RuntimeError',1) and len(calls)==1

def test_short_controller_transport_failure_does_not_flicker_to_unknown(environment):
    app,client,_,_=environment;enroll(environment);calls=[]
    def rpc(path):
        calls.append(path)
        if len(calls)==1:raise RuntimeError('fixture transport failure')
        return report()
    app.state.rpc=rpc
    data=client.get('/api/players').json();assert data['online_count']==1 and data['players'][0]['online'] is True and len(calls)==2

def test_unavailable_snapshot_retains_only_play_time_already_observed(environment):
    app,client,_,_=environment;enroll(environment);st=app.state.store;now=time.time()
    with st.db() as db:db.execute('INSERT INTO players(uuid,name,first_seen,last_seen,online_since,play_seconds) VALUES(?,?,?,?,?,?)',(IDENTIFIER,'FixturePlayer',now-500,now-5,now-105,120))
    app.state.rpc=lambda path:(_ for _ in ()).throw(RuntimeError('fixture unavailable'))
    first=client.get('/api/players').json();second=client.get('/api/players').json()
    assert first['players'][0]['online'] is None and first['players'][0]['online_since'] is None
    assert first['players'][0]['play_seconds']==220 and second['players'][0]['play_seconds']==220
    with st.db() as db:assert db.execute("SELECT COUNT(*) FROM events WHERE event='player_presence_unavailable'").fetchone()[0]==1

import json,time
import pytest
from mcj import greetings,player_events
from test_security import environment,enroll,post

ID='00000000-0000-0000-0000-000000000001'
def batch(key='join-1',at=None,event='player_login'):
    return {'cursor':{'offset':1},'records':[{'key':key,'uuid':ID,'name':'Fixture','event':event,'at':time.time() if at is None else at}]}

def test_first_and_return_survive_deduplication_and_event_retention(environment):
    st=environment[0].state.store;first=player_events.ingest(st,batch())
    assert first[0]['first'] is True
    assert player_events.ingest(st,batch())==[]
    with st.db() as db:db.execute("DELETE FROM events WHERE category='player'")
    again=player_events.ingest(st,batch('join-2'))
    assert again[0]['first'] is False

def test_greetings_disabled_by_default_and_literal_json_delivery(environment):
    st=environment[0].state.store;calls=[]
    arrivals=player_events.ingest(st,batch())
    rpc=lambda path,data:calls.append((path,data))
    greetings.send(st,rpc,arrivals);assert calls==[]
    cfg={**greetings.DEFAULTS,'first_enabled':True,'first_message':'Hi {player}! "clickEvent": {"action":"run_command"}'}
    st.set('greetings',cfg);greetings.send(st,rpc,arrivals)
    path,payload=calls[0];assert path=='/console'
    assert payload['command'].startswith('tellraw Fixture ')
    component=json.loads(payload['command'].split(' ',2)[2])
    assert set(component)=={'text'} and 'Hi Fixture!' in component['text']
    cfg.update(first_enabled=False,return_enabled=True,return_message='Welcome back, {player}')
    st.set('greetings',cfg);greetings.send(st,rpc,[{**arrivals[0],'first':False}])
    assert json.loads(calls[-1][1]['command'].split(' ',2)[2])=={'text':'Welcome back, Fixture'}

def test_stale_events_and_failed_delivery_are_not_replayed(environment):
    st=environment[0].state.store;st.set('greetings',{**greetings.DEFAULTS,'first_enabled':True})
    arrivals=player_events.ingest(st,batch(at=1000));calls=[]
    greetings.send(st,lambda *a:calls.append(a),arrivals,now=1200);assert calls==[]
    def fail(*a):raise RuntimeError('connection unavailable')
    greetings.send(st,fail,[{**arrivals[0],'at':1200}],now=1200)
    assert player_events.ingest(st,batch())==[]

def test_greeting_settings_require_admin_csrf_and_validate_input(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    cfg={**greetings.DEFAULTS,'first_enabled':True,'return_enabled':True}
    assert post(client,'/api/settings',{'section':'greetings','value':cfg}).status_code==403
    assert post(client,'/api/settings',{'section':'greetings','value':cfg},csrf).status_code==200
    assert client.get('/api/settings').json()['greetings']==cfg
    for change in [{'first_message':''},{'first_message':'x'*501},{'first_enabled':'true'},{'return_message':'\x00'}]:
        assert post(client,'/api/settings',{'section':'greetings','value':cfg|change},csrf).status_code==400
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,'/api/settings',{'section':'greetings','value':cfg},csrf).status_code==403

import pytest
from pydantic import ValidationError
from mcj import game_rules
from test_security import environment,enroll,post

def fake_rcon(values,commands):
    def run(command):
        commands.append(command);parts=command.split(' ');key=parts[1].removeprefix('minecraft:')
        if key not in values:return 'Unknown game rule'
        if len(parts)==3:values[key]=parts[2]=='true';return 'Game rule '+key+' is now set to '+parts[2]+'\n'
        return 'Game rule '+key+' is currently set to '+str(values[key]).lower()+'\n'
    return run

def test_read_unknown_rules_are_disabled_and_query_never_changes_values():
    values={'locator_bar':False,'keep_inventory':True,'advance_time':True};commands=[]
    data=game_rules.read(fake_rcon(values,commands),'26.3','world','container-a')
    assert next(x for x in data['rules'] if x['key']=='locator_bar')['enabled'] is False
    assert next(x for x in data['rules'] if x['key']=='spawn_mobs')['supported'] is False
    assert all(len(x.split(' '))==2 for x in commands)

def test_version_specific_names_and_typed_optimistic_update():
    assert game_rules.command_key('advance_time','1.21.1')=='doDaylightCycle'
    assert game_rules.command_key('advance_time','1.21.11')=='minecraft:advance_time'
    assert game_rules.command_key('locator_bar','26.3')=='minecraft:locator_bar'
    with pytest.raises(ValueError):game_rules.command_key('locator_bar','1.21.1')
    values={'locator_bar':False};commands=[];rcon=fake_rcon(values,commands)
    data=game_rules.Change(key='locator_bar',enabled=True,expected=False,basis=game_rules.basis('26.3','world','a'))
    assert game_rules.apply(rcon,data,'26.3','world','a')['enabled'] is True
    assert commands==['gamerule minecraft:locator_bar','gamerule minecraft:locator_bar true','gamerule minecraft:locator_bar']
    with pytest.raises(ValueError,match='game_rules_changed'):game_rules.apply(rcon,data,'26.3','world','a')
    commands.clear()
    with pytest.raises(ValueError,match='game_rules_changed'):game_rules.apply(rcon,data,'26.3','other-world','a')
    assert not commands

@pytest.mark.parametrize('version,key,response,expected',[
    ('1.21.1','natural_health_regeneration','Gamerule naturalRegeneration is currently set to: true',True),
    ('1.21.1','keep_inventory','Gamerule keepInventory is currently set to: false',False),
    ('26.3','natural_health_regeneration','Gamerule minecraft:natural_health_regeneration is currently set to: true',True),
    ('26.3','keep_inventory','Game rule keep_inventory is currently set to false\n',False),
])
def test_native_server_rule_response_spelling_and_colon(version,key,response,expected):
    commands=[]
    def rcon(command):
        commands.append(command)
        return response
    assert game_rules.query(rcon,key,version) is expected
    assert commands==['gamerule '+game_rules.command_key(key,version)]

@pytest.mark.parametrize('response',[
    'Gamerule keepInventory is currently set to: true',
    'Gamerule naturalRegeneration is currently set to: unknown',
    'Gamerule naturalRegeneration is currently set to: true\nextra output',
    'Changed naturalRegeneration to true',
])
def test_rule_response_stays_bound_to_the_exact_rule_and_boolean(response):
    with pytest.raises(ValueError,match='unsupported_game_rule'):
        game_rules.query(lambda command:response,'natural_health_regeneration','1.21.1')

@pytest.mark.parametrize('payload',[{'key':'locator_bar;stop','enabled':True,'expected':False,'basis':'a'*64},{'key':'locator_bar','enabled':'false','expected':False,'basis':'a'*64},{'key':'locator_bar','enabled':True,'expected':False,'basis':'a'*64,'command':'stop'}])
def test_game_rule_input_cannot_become_arbitrary_commands(payload):
    with pytest.raises(ValidationError):game_rules.Change(**payload)

def test_admin_csrf_and_audit_for_game_rule_changes(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];calls=[]
    def rpc(path,payload=None):
        calls.append((path,payload))
        return {'key':'locator_bar','enabled':False,'previous':True,'world':'world'} if payload else {'rules':[]}
    app.state.rpc=rpc
    assert client.get('/api/server/game-rules').status_code==200
    data={'key':'locator_bar','enabled':False,'expected':True,'basis':'a'*64}
    assert post(client,'/api/server/game-rules',data).status_code==403
    assert post(client,'/api/server/game-rules',data,csrf).status_code==200
    assert calls[-1]==('/game-rules',data)
    with app.state.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE event='game_rule_changed'").fetchone()[0]==1
        db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert client.get('/api/server/game-rules').status_code==403
    assert post(client,'/api/server/game-rules',data,csrf).status_code==403

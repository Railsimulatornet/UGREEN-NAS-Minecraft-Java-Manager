"""A small typed game-rule interface; never accepts an arbitrary RCON command."""
import hashlib,json,re
from pydantic import BaseModel,Field,StrictBool

RULES={
    'locator_bar':'locatorBar',
    'keep_inventory':'keepInventory',
    'advance_time':'doDaylightCycle',
    'advance_weather':'doWeatherCycle',
    'mob_griefing':'mobGriefing',
    'natural_health_regeneration':'naturalRegeneration',
    'immediate_respawn':'doImmediateRespawn',
    'show_death_messages':'showDeathMessages',
    'spawn_mobs':'doMobSpawning',
}

class Change(BaseModel):
    model_config={'extra':'forbid'}
    key:str=Field(pattern='^('+'|'.join(RULES)+')$')
    enabled:StrictBool
    expected:StrictBool
    basis:str=Field(pattern=r'^[a-f0-9]{64}$')

def command_key(key,version):
    if key not in RULES:raise ValueError('unsupported_game_rule')
    if re.fullmatch(r'\d{2}\.\d+(?:\.\d+)?',version):modern=True
    else:
        match=re.fullmatch(r'1\.(\d+)(?:\.(\d+))?',version)
        if not match:raise ValueError('unsupported_game_rule_version')
        minor,patch=int(match[1]),int(match[2] or 0)
        if key=='locator_bar' and (minor,patch)<(21,6):raise ValueError('unsupported_game_rule')
        modern=(minor,patch)>=(21,11)
    return 'minecraft:'+key if modern else RULES[key]

def query(rcon,key,version):
    name=command_key(key,version)
    output=rcon('gamerule '+name)
    expected_name=name.removeprefix('minecraft:')
    match=re.fullmatch(r'(?:Game rule|Gamerule) (?:minecraft:)?'+re.escape(expected_name)+r' is currently set to:?\s+(true|false)\s*',output)
    if not match:raise ValueError('unsupported_game_rule')
    return match[1]=='true'

def basis(version,world,container_id):
    return hashlib.sha256(json.dumps([version,world,container_id],separators=(',',':')).encode()).hexdigest()

def read(rcon,version,world,container_id):
    records=[]
    for key in RULES:
        try:records.append({'key':key,'enabled':query(rcon,key,version),'supported':True})
        except ValueError:records.append({'key':key,'enabled':None,'supported':False})
    return {'world':world,'version':version,'basis':basis(version,world,container_id),'rules':records}

def apply(rcon,data,version,world,container_id):
    if data.basis!=basis(version,world,container_id):raise ValueError('game_rules_changed')
    previous=query(rcon,data.key,version)
    if previous!=data.expected:raise ValueError('game_rules_changed')
    if previous!=data.enabled:
        rcon('gamerule '+command_key(data.key,version)+' '+str(data.enabled).lower())
        if query(rcon,data.key,version)!=data.enabled:raise ValueError('game_rule_not_applied')
    return {'key':data.key,'enabled':data.enabled,'previous':previous,'world':world}

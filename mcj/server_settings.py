"""Server-managed values and validation for the editable Minecraft properties."""
import re

PROTECTED={'online-mode':'true','gamemode':'spectator','force-gamemode':'true',
           'server-ip':'','server-port':'25565','enable-rcon':'true','rcon.port':'25575',
           'enable-query':'false','enable-jmx-monitoring':'false','management-server-enabled':'false'}
SECRET_KEYS={'rcon.password','management-server-secret','management-server-tls-keystore-password'}

def normalize(current,proposed):
    result={**current,**proposed}
    from .memory_budget import limits,JAVA_RESERVE_MB
    if 'container_memory_mb' in proposed and 'memory_mb' not in proposed:
        if type(proposed['container_memory_mb']) is not int:raise ValueError('invalid_container_memory_budget')
        result['memory_mb']=proposed['container_memory_mb']-JAVA_RESERVE_MB
    limits(result)
    properties={**current.get('properties',{}),**proposed.get('properties',{})}
    if len(properties)>300:raise ValueError('invalid_server_properties')
    clean={}
    for key,value in properties.items():
        if not isinstance(key,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,80}',key):raise ValueError('invalid_server_property')
        if key in SECRET_KEYS:
            # Secrets are generated and stored separately, never accepted from this GUI.
            if key in proposed.get('properties',{}):raise ValueError('protected_server_property')
            continue
        if type(value) not in [str,int,bool]:raise ValueError('invalid_server_property')
        value=str(value).lower() if type(value) is bool else str(value)
        if len(value)>4000 or any(c in value for c in ['\r','\n','\x00']):raise ValueError('invalid_server_property')
        if key=='white-list':
            from .player_admission import whitelist_value
            value=whitelist_value(value)
        if key in PROTECTED and value!=PROTECTED[key]:raise ValueError('protected_server_property')
        if key in ['view-distance','simulation-distance'] and (not value.isdigit() or not 2<=int(value)<=32):raise ValueError('invalid_chunk_distance')
        clean[key]=value
    world=clean.get('level-name',result.get('world','world'))
    if not isinstance(world,str) or not re.fullmatch('[A-Za-z0-9_-]{1,60}',world):raise ValueError('invalid_world_name')
    clean.update(PROTECTED)
    clean['level-name']=world
    if result.get('version','').startswith('26.'):
        if 'pause-when-empty-seconds' in proposed.get('properties',{}) and clean.get('pause-when-empty-seconds')!='0':
            raise ValueError('protected_server_property')
        clean['pause-when-empty-seconds']='0'
    result.update(properties=clean,world=world)
    return result

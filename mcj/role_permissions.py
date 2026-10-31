"""Bounded in-game abilities; never grant OP or web administrator rights."""
import json
from .project_paths import project_path
from .store import Store

ABILITIES=('kick','announce','time','weather')
ROLES=('visitor','player','moderator','administrator')


def defaults():
    return {'visitor':[],'player':[],'moderator':['kick','announce'],'administrator':list(ABILITIES)}


def normalize(value):
    if not isinstance(value,dict) or set(value)!=set(ROLES):raise ValueError('invalid_role_permissions')
    result={}
    for role in ROLES:
        granted=value[role]
        if not isinstance(granted,list) or len(granted)>len(ABILITIES):raise ValueError('invalid_role_permissions')
        if any(not isinstance(x,str) or x not in ABILITIES for x in granted) or len(set(granted))!=len(granted):raise ValueError('invalid_role_permissions')
        if role=='visitor' and granted:raise ValueError('visitor_permissions_are_fixed')
        result[role]=[x for x in ABILITIES if x in granted]
    return result


def read(root):
    path=project_path(root,'control/roles/permissions.json')
    if not path.exists():return {'format':1,'roles':defaults(),'configured':False}
    if path.is_symlink() or path.stat().st_size>65536:raise ValueError('invalid_role_permissions')
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('format')!=1:raise ValueError('invalid_role_permissions')
        return {'format':1,'roles':normalize(value['roles']),'configured':True}
    except (ValueError,KeyError,TypeError):raise ValueError('invalid_role_permissions') from None


def write(root,value):
    value={'format':1,'roles':normalize(value)}
    Store.atomic(project_path(root,'control/roles/permissions.json'),json.dumps(value,sort_keys=True).encode(),0o640)
    return {**value,'configured':True}

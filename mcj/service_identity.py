"""Per-installation numeric identity, checked against the NAS before creating files."""
import os
import re
import secrets

def validate(uid,gid):
    if any(type(x) is not int or not 1<=x<2**31 for x in (uid,gid)):raise ValueError('service_identity_invalid')
    return uid,gid

def allocated(passwd,groups,reserved=(),previous=None):
    if any(not isinstance(x,str) or len(x)>2*1024*1024 for x in (passwd,groups)):raise ValueError('service_identity_inventory_invalid')
    def ids(text):
        result=set()
        for line in text.splitlines():
            if not line or line.startswith('#'):continue
            fields=line.split(':')
            if len(fields)<4 or not fields[2].isdigit():raise ValueError('service_identity_inventory_invalid')
            result.add(int(fields[2]))
        return result
    users=ids(passwd);group_ids=ids(groups);other=set(reserved)
    for line in passwd.splitlines():
        if line and not line.startswith('#'):
            fields=line.split(':')
            if not fields[3].isdigit():raise ValueError('service_identity_inventory_invalid')
            group_ids.add(int(fields[3]))
    if previous is not None:
        uid,gid=validate(*previous)
        if uid in users|other or gid in group_ids|other:raise ValueError('service_identity_collision')
        return uid,gid
    for _ in range(100):
        chosen=200000+secrets.randbelow(100000)
        if chosen not in users|group_ids|other:return chosen,chosen
    raise ValueError('service_identity_unavailable')

def current():
    uid=os.getuid() if hasattr(os,'getuid') else 1009
    gid=os.getgid() if hasattr(os,'getgid') else 10
    return validate(int(os.environ.get('MCJ_SERVICE_UID',uid)),int(os.environ.get('MCJ_SERVICE_GID',gid)))

def user():return ':'.join(map(str,current()))

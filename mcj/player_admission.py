"""An explicit choice between a name list and protected, previously unknown players."""
import hashlib
import json

def whitelist_value(value):
    if type(value) is bool:return str(value).lower()
    if isinstance(value,str) and value.lower() in {'true','false'}:return value.lower()
    raise ValueError('invalid_server_property')

def guard_matches_runtime(runtime,trusted_guard):
    tested=trusted_guard.get('tested_loaders')
    return (isinstance(runtime,dict) and isinstance(tested,list)
            and trusted_guard.get('minecraft')==runtime.get('version')
            and trusted_guard.get('loader')==runtime.get('loader')
            and trusted_guard.get('runtime_test')=='passed'
            and runtime.get('loader_version') in tested
            and trusted_guard.get('java')==runtime.get('java'))

def require_target(properties,trusted_guard,runtime=None):
    # An already-open source is not proof for a different target artifact.
    value=whitelist_value(properties.get('white-list'))
    if value=='false':
        if not guard_matches_runtime(runtime,trusted_guard):
            raise ValueError('guard_runtime_combination_not_tested')
        if (trusted_guard.get('visitor_verified') is not True
                or trusted_guard.get('visitor_client_test')!='passed'):
            raise ValueError('visitor_admission_requires_verified_guard')
    return value

def opens_to_new_players(current, proposed):
    return (str(current.get('properties',{}).get('white-list','true')).lower()!='false'
            and str(proposed.get('properties',{}).get('white-list','true')).lower()=='false')

def require_verified(ready):
    if ready.get('ready') is not True or ready.get('visitor_verified') is not True:
        raise ValueError('visitor_admission_requires_verified_guard')

def view(configuration, properties, ready):
    return {'open_to_new_players':str(properties.get('white-list','true')).lower()=='false',
            'configured_open':str(configuration.get('properties',{}).get('white-list','true')).lower()=='false',
            'can_open':ready.get('ready') is True and ready.get('visitor_verified') is True,
            'guard_sha256':ready.get('guard_sha256'),
            'online_mode':str(properties.get('online-mode','false')).lower()=='true',
            'basis':hashlib.sha256(json.dumps(configuration,sort_keys=True).encode()).hexdigest()}

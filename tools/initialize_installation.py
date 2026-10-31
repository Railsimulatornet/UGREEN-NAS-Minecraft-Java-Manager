"""Initialize one empty services-v1 tree; stdin is private, never a log source."""
import hashlib
import json
import os
from pathlib import Path
import time

from mcj.store import Store
from mcj import mods, properties


def initialize(root, config, password):
    root = Path(root)
    state = root / 'manager/state'
    if (state / 'manager.sqlite3').exists() or (state / '.initial-accounts.fernet').exists():
        raise RuntimeError('installation_already_initialized')
    if any((state / name).is_symlink() for name in ['manager.sqlite3', '.initial-accounts.fernet']):
        raise RuntimeError('unsafe_installation_path')
    guard = json.loads((root / 'mcj_controller/control/runtime/guard.json').read_text())
    raw = (root / 'mcj_minecraft/data/mods' / guard['filename']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != guard['sha256']:
        raise RuntimeError('guard_artifact_integrity_failed')
    meta = mods.inspect_jar(raw)
    if not any(item['id'] == 'mcj_guard' for item in meta['mods']):
        raise RuntimeError('guard_artifact_missing')
    runtime = {
        'version': '26.3', 'java': 25, 'loader': 'NEOFORGE',
        'loader_version': '26.3.0.99', 'memory_mb': 6144, 'world': 'world',
        'properties': {'online-mode': 'true', 'gamemode': 'spectator',
                       'force-gamemode': 'true', 'white-list': 'true',
                       'difficulty': 'normal', 'pvp': 'false', 'max-players': '20'}}
    if 'container_memory_mb' in config:
        budget=config['container_memory_mb']
        if type(budget) is not int or not 4096<=budget<=65536 or budget%1024:raise ValueError('initial_memory_invalid')
        runtime['container_memory_mb']=budget;runtime['memory_mb']=budget-2048
    st = Store(state, root / 'manager/secrets/encryption', state / '.initial-accounts.fernet',
               initial_accounts=[{'username': config['username'], 'email': config['email'],
                                  'password': password}])
    st.set('server', runtime)
    from mcj.guard_bundle import read as bundled_guards
    st.set('guard_catalog',bundled_guards())
    st.set('web_access',{'address':config['origin'],'external_web':False})
    st.set('setup_wizard',{'enabled':True,'completed':False,'step':0})
    st.set('smtp', {'host': '', 'port': 587, 'security': 'starttls',
                    'username': '', 'sender': '', 'password': ''}, True)
    # Fresh projects inherit no acceptance verdict from another NAS or mod configuration.
    st.set('release', {'status': 'internal_validation', 'public_web': False,
                      'public_game': False, 'visitor_verified': False,
                      'restore_verified': False, 'security_verified': False})
    st.set('maintenance', {'automatic': False, 'check_minutes': 30, 'backup_minutes': 30,
                           'retention_days': 14, 'backup_enabled': True})
    with st.db() as db:
        if config.get('initial_password_chosen') is True:
            db.execute('UPDATE users SET force_password=0 WHERE username=?',(config['username'],))
        db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,enabled,installed_enabled,updated) '
                   'VALUES(?,?,?,?,?,?,?,?,?)', (guard['sha256'], guard['filename'], guard['sha256'],
                                                json.dumps(meta), 'system', 'installed', 1, 1, time.time()))
    Store.atomic(root / 'mcj_controller/control/runtime/runtime.json',
                 json.dumps(runtime).encode(), 0o640)
    rcon = (root / 'manager/secrets/rcon').read_text().strip()
    server = dict(runtime['properties'], **{
        'enforce-whitelist': 'true', 'enable-rcon': 'true', 'rcon.password': rcon,
        'rcon.port': '25575', 'broadcast-rcon-to-ops': 'false', 'server-port': '25565',
        'server-ip': '', 'level-name': 'world', 'spawn-protection': '16',
        'enable-command-block': 'false', 'enforce-secure-profile': 'true',
        'enable-query': 'false', 'view-distance': '8', 'simulation-distance': '6',
        'allow-flight': 'false', 'pause-when-empty-seconds': '0',
        'motd': 'MCJ Manager - Einrichtung'})
    Store.atomic(root / 'mcj_minecraft/data/server.properties',
                 properties.dumps(server).encode(), 0o600)
    Store.atomic(root / 'mcj_minecraft/data/whitelist.json', b'[]', 0o600)
    Store.atomic(root / 'mcj_minecraft/data/ops.json', b'[]', 0o600)
    Store.atomic(root / 'mcj_controller/control/roles/network-access.json',b'{"public_game":false}',0o640)
    return {'initialized': True, 'accounts': 1, 'runtime': {key: runtime[key] for key in
            ['version', 'java', 'loader', 'loader_version']}, 'public_access': False}


if __name__ == '__main__':
    import sys
    payload = json.load(sys.stdin)
    try:
        print(json.dumps(initialize('/project', payload['config'], payload['password'])))
    except Exception as error:
        # Never include stdin, account values or exception repr in container/terminal logs.
        print(json.dumps({'initialized': False, 'error': type(error).__name__}))
        raise SystemExit(1)

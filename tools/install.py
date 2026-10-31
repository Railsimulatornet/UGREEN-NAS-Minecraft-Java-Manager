#!/usr/bin/env python3
"""Guided fresh installation. Existing UGOS projects are always refused unchanged."""
import argparse
import base64
import getpass
import hashlib
import json
import ipaddress
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

PROJECT = 'ugreen_minecraft_java'
CONTAINER_NAMES={'mcj_manager','mcj_controller','mcj_minecraft'}
UID, GID = 1009, 10
BUNDLE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BUNDLE))
from mcj import __version__
GAME_IMAGE = 'itzg/minecraft-server:java25@sha256:6fd6f9bb6998b7cd06948ec6ab03fabfdf98ba3f2ec030c44069bec9a6bdf09d'



def configure_identity(uid,gid):
    from mcj.service_identity import validate
    global UID,GID
    UID,GID=validate(uid,gid)

def select_identity(image=None,previous=None):
    from mcj.service_identity import allocated
    if image is None:
        passwd=Path('/etc/passwd').read_text();groups=Path('/etc/group').read_text();reserved=[]
    else:
        script="import json;print(json.dumps([open('/host-passwd').read(),open('/host-group').read()]))"
        response=docker('run','--rm','--network','none','--user','65534:65534','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--memory','64m','--pids-limit','16','--mount','type=bind,src=/etc/passwd,dst=/host-passwd,readonly',
            '--mount','type=bind,src=/etc/group,dst=/host-group,readonly','--entrypoint','python',image,'-c',script,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        passwd,groups=json.loads(response.stdout)
        identifiers=docker('ps','-aq',stdout=subprocess.PIPE,text=True).stdout.split();reserved=[]
        rows=json.loads(docker('inspect',*identifiers,stdout=subprocess.PIPE,text=True).stdout) if identifiers else []
        for row in rows:
            values=[row.get('Config',{}).get('User','')]
            values.extend(x.split('=',1)[1] for x in row.get('Config',{}).get('Env',[]) if x.split('=',1)[0] in {'UID','GID','PUID','PGID'} and '=' in x)
            for value in values:
                reserved.extend(int(x) for x in str(value).split(':') if x.isdigit())
    uid,gid=allocated(passwd,groups,reserved,previous)
    configure_identity(uid,gid)
    return {'service_uid':uid,'service_gid':gid,'host_collision_check':True}

def validate(config):
    required={'root', 'backup_root', 'origin', 'username', 'email', 'accept_eula'}
    if not required<=set(config) or set(config)-required-{'trusted_proxies','local_networks','game_bind_address'}:
        raise ValueError('setup_fields_invalid')
    for key in ['root', 'backup_root']:
        value = config[key]
        if not isinstance(value, str) or not re.fullmatch(r'/volume[1-9][0-9]*/[A-Za-z0-9_./-]+', value):
            raise ValueError('setup_path_invalid')
        p = PurePosixPath(value)
        if '..' in p.parts or str(p) != value or len(p.parts) < 4:
            raise ValueError('setup_path_invalid')
        for parent in [Path(value), *Path(value).parents]:
            if parent.is_symlink():
                raise ValueError('setup_symlink_refused')
    root, backup = PurePosixPath(config['root']), PurePosixPath(config['backup_root'])
    if root == backup or root in backup.parents or backup in root.parents:
        raise ValueError('setup_paths_overlap')
    origin = urlsplit(config['origin'])
    if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
            or origin.query or origin.fragment or origin.path not in ['', '/']
            or not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]{1,5})?', origin.netloc)):
        raise ValueError('setup_https_origin_required')
    if origin.port is not None and not 1 <= origin.port <= 65535:
        raise ValueError('setup_https_origin_required')
    if not isinstance(config['username'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{2,40}', config['username']):
        raise ValueError('setup_username_invalid')
    if not isinstance(config['email'], str) or len(config['email']) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', config['email']):
        raise ValueError('setup_email_invalid')
    if config['accept_eula'] is not True:
        raise ValueError('setup_eula_required')
    try:
        proxies=','.join(str(ipaddress.ip_address(value.strip())) for value in config.get('trusted_proxies','').split(',') if value.strip())
        networks=','.join(str(ipaddress.ip_network(value.strip(),strict=True)) for value in config.get('local_networks','').split(',') if value.strip())
        if proxies and any(ipaddress.ip_address(value).is_unspecified or ipaddress.ip_address(value).is_multicast for value in proxies.split(',')):raise ValueError()
        private=[ipaddress.ip_network(value) for value in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','fc00::/7']]
        if networks and any(not any(ipaddress.ip_network(value).subnet_of(parent) for parent in private if parent.version==ipaddress.ip_network(value).version) for value in networks.split(',')):raise ValueError()
        if len(proxies.split(','))>10 or len(networks.split(','))>10:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('setup_proxy_network_invalid') from None
    try:
        game_bind=ipaddress.ip_address(config.get('game_bind_address','127.0.0.1'))
        if game_bind.version!=4 or not (game_bind.is_loopback or any(game_bind in parent for parent in private if parent.version==4)):raise ValueError()
    except (ValueError,TypeError):raise ValueError('setup_game_binding_invalid') from None
    return dict(config, origin=config['origin'].rstrip('/'),trusted_proxies=proxies,local_networks=networks,game_bind_address=str(game_bind))


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], check=True, **kwargs)


def refuse_existing_project():
    # Read only: resolve actual labels before doing anything to an existing project.
    ids = docker('ps', '-aq', stdout=subprocess.PIPE, text=True).stdout.split()
    if ids:
        existing = json.loads(docker('inspect', *ids, stdout=subprocess.PIPE, text=True).stdout)
        for item in existing:
            labels = item['Config'].get('Labels') or {}
            if labels.get('com.docker.compose.project') == PROJECT or item['Name'].lstrip('/') in CONTAINER_NAMES:
                raise RuntimeError('existing_project_refused: project=' + str(labels.get('com.docker.compose.project'))
                                   + ', service=' + str(labels.get('com.docker.compose.service')))


def preflight(config,check_ports=True):
    refuse_existing_project()
    for key in ['root', 'backup_root']:
        target = Path(config[key])
        if target.exists() or target.is_symlink():
            raise RuntimeError('existing_installation_path_refused')
        if not target.parent.is_dir():
            raise RuntimeError('installation_parent_missing')
    for address,port in ([('127.0.0.1',8090),(config.get('game_bind_address','127.0.0.1'),25565)] if check_ports else []):
        with socket.socket() as probe:
            probe.bind((address, port))
    guard = json.loads((BUNDLE / 'artifacts/guard.json').read_text())
    if (guard['minecraft'], guard['loader']) != ('26.3', 'NEOFORGE') or guard.get('dependencies'):
        raise RuntimeError('installation_guard_incompatible')
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+\.jar', guard['filename']):
        raise RuntimeError('installation_guard_invalid')
    raw = (BUNDLE / 'artifacts' / guard['filename']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != guard['sha256']:
        raise RuntimeError('installation_guard_invalid')
    docker('compose', 'version', stdout=subprocess.DEVNULL)
    return guard, raw


def compose_text(config, socket_gid):
    template = (BUNDLE / 'compose.yaml').read_text(encoding='utf-8')
    template = template.replace('1009:10',str(UID)+':'+str(GID)).replace('UID: \"1009\"','UID: '+json.dumps(str(UID))).replace('GID: \"10\"','GID: '+json.dumps(str(GID)))
    # One pass: neither placeholder may rewrite a path inserted for the other.
    paths={'/volume1/docker/minecraftjava-backups':config['backup_root'],
           '/volume1/docker/minecraftjava':config['root']}
    template=re.sub('|'.join(re.escape(key) for key in paths),lambda match:paths[match[0]],template)
    template = template.replace('APP_ORIGIN: http://localhost:18090', 'APP_ORIGIN: ' + json.dumps(config['origin']))
    template = template.replace('MCJ_TRUSTED_PROXIES: ""','MCJ_TRUSTED_PROXIES: '+json.dumps(config.get('trusted_proxies','')))
    template = template.replace('MCJ_LOCAL_NETWORKS: ""','MCJ_LOCAL_NETWORKS: '+json.dumps(config.get('local_networks','')))
    template = template.replace('GAME_BIND_ADDRESS: "127.0.0.1"','GAME_BIND_ADDRESS: '+json.dumps(config.get('game_bind_address','127.0.0.1')))
    template = template.replace('127.0.0.1:25565:25565/tcp',config.get('game_bind_address','127.0.0.1')+':25565:25565/tcp')
    template = template.replace("'localhost:18090'", repr(urlsplit(config['origin']).netloc))
    template = template.replace('group_add: ["121"]', 'group_add: ["' + str(int(socket_gid)) + '"]')
    return template


def prepare(config, guard, raw, socket_gid):
    root, backup = Path(config['root']), Path(config['backup_root'])
    os.umask(0o077)
    root.mkdir(mode=0o750)  # exclusive; never merge into an existing installation
    directories = ['manager/source', 'manager/state', 'manager/staging', 'manager/secrets',
                   'mcj_minecraft/data/mods', 'mcj_minecraft/mods', 'mcj_minecraft/disabled',
                   'mcj_controller/control/runtime', 'mcj_controller/control/roles',
                   'mcj_controller/control/reports', 'mcj_controller/releases/guards/neoforge-26.3',
                   'mcj_controller/.install']
    for name in directories:
        (root / name).mkdir(parents=True, exist_ok=True, mode=0o750)
    backup.mkdir(mode=0o700)
    source = root / 'manager/source'
    for name in ['mcj', 'tools', 'deploy', 'artifacts', 'compose.yaml', 'NOTICE.txt', 'LICENSE', 'requirements.txt', 'Dockerfile', '.dockerignore', 'start-game.sh']:
        src, dst = BUNDLE / name, source / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        else:
            shutil.copyfile(src, dst)
        if name=='start-game.sh':dst.chmod(0o550)
    def write(name, data, mode=0o640):
        p = root / name
        with p.open('xb') as stream:
            stream.write(data.encode() if isinstance(data, str) else data)
        p.chmod(mode)
    write('manager/state/service-identity.json',json.dumps({'uid':UID,'gid':GID,'host_collision_check':True}),0o600)
    write('docker-compose.yaml', compose_text(config, socket_gid))
    write('.env', 'MCJ_GAME_IMAGE=' + GAME_IMAGE + '\n', 0o600)
    write('manager/secrets/encryption', base64.urlsafe_b64encode(os.urandom(32)), 0o400)
    write('manager/secrets/rpc', secrets.token_urlsafe(48), 0o400)
    write('manager/secrets/rcon', secrets.token_urlsafe(40), 0o400)
    guard = dict(guard, path='releases/guards/neoforge-26.3/' + guard['filename'],
                 runtime_test='not_tested', visitor_verified=False, visitor_client_test='not_verified')
    write('mcj_minecraft/data/mods/' + guard['filename'], raw, 0o440)
    write('mcj_controller/' + guard['path'], raw, 0o440)
    write('mcj_controller/releases/guards/registry.json', json.dumps({'artifacts': [guard]}))
    write('mcj_controller/control/runtime/guard.json', json.dumps(guard))
    write('mcj_controller/control/runtime/guard.sha256', guard['sha256'] + '  ' + guard['filename'] + '\n')
    write('mcj_controller/control/runtime/start.sh', (BUNDLE / 'start-game.sh').read_bytes(), 0o550)
    write('mcj_controller/control/roles/roles.json', '{}')
    write('mcj_controller/control/roles/maintenance.json', '{"closed":false}')
    for p in [root, *root.rglob('*'), backup]:
        if p.is_symlink():
            raise RuntimeError('setup_symlink_refused')
        os.chown(p, UID, GID)
    (root / 'manager/secrets').chmod(0o700)
    return root / 'docker-compose.yaml'


def interactive():
    print('MCJ Manager ' + __version__ + ' – neue Installation vorbereiten')
    print('Bestehende Projekte und Proxys werden nicht verändert. HTTPS-Zugang erforderlich.')
    config = {key: input(prompt).strip() for key, prompt in [
        ('root', 'Neuer Projektordner (z. B. /volume1/docker/minecraftjava): '),
        ('backup_root', 'Neuer Backupordner (übergeordneter Ordner muss bestehen): '),
        ('origin', 'HTTPS-Adresse des Managers (z. B. https://minecraft.example.de): '),
        ('username', 'Name des ersten Webadministrators: '), ('email', 'Seine E-Mail-Adresse: ')]}
    config['trusted_proxies']=input('Bestätigte IP des HTTPS-Proxys aus Sicht des Managers (leer bei direktem Zugang): ').strip()
    config['local_networks']=input('Direkte Heimnetzbereiche (z. B. 192.168.1.0/24; leer beim Zugang über den Proxy): ').strip()
    config['game_bind_address']=input('Heimnetz-IP dieses NAS für Minecraft (leer: nur auf dem NAS): ').strip() or '127.0.0.1'
    print('Minecraft-EULA: https://www.minecraft.net/eula')
    config['accept_eula'] = input('Minecraft-EULA gelesen und akzeptiert? (ja/nein): ').strip().lower() == 'ja'
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='JSON mit Pfaden/Adresse/Konto, niemals mit Passwörtern')
    parser.add_argument('--check', action='store_true', help='Nur lesende Vorprüfung; keine Dateien/Images erzeugen')
    args = parser.parse_args()
    config = validate(json.loads(args.config.read_text()) if args.config else interactive())
    guard, raw = preflight(config)
    if args.check:
        print('Vorprüfung bestanden. Es wurde nichts angelegt oder gestartet.')
        return
    if os.name == 'nt' or os.geteuid() != 0:
        raise RuntimeError('run_as_root_on_nas')
    select_identity()
    password = getpass.getpass('Vorläufiges Passwort (mindestens 12 Zeichen): ')
    if not 12 <= len(password) <= 128 or password != getpass.getpass('Passwort wiederholen: '):
        raise ValueError('initial_password_invalid')
    compose = prepare(config, guard, raw, os.stat('/var/run/docker.sock').st_gid)
    prefix = ['compose', '-p', PROJECT, '-f', str(compose)]
    docker(*prefix, 'config', '--quiet')
    # This script refuses existing projects; the explicit name is for this new project only.
    refuse_existing_project()
    docker(*prefix, 'build', 'manager')
    docker('pull', GAME_IMAGE)
    image_id = docker('image', 'inspect', GAME_IMAGE, '--format', '{{.Id}}',
                      stdout=subprocess.PIPE, text=True).stdout.strip()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise RuntimeError('game_image_identity_invalid')
    display_image = 'itzg/minecraft-server:java25-mcj-' + image_id[7:19]
    docker('image', 'tag', GAME_IMAGE, display_image)
    environment = Path(config['root']) / '.env'
    environment.write_text('MCJ_GAME_IMAGE=' + display_image + '\n', encoding='utf-8')
    environment.chmod(0o600)
    seed = "import runpy; runpy.run_path('/setup/initialize_installation.py',run_name='__main__')"
    result = docker('run', '--rm', '-i', '--log-driver', 'none', '--network', 'none',
                    '--user', str(UID) + ':' + str(GID), '--read-only', '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges:true', '--tmpfs', '/tmp:rw,nosuid,noexec,size=64m',
                    '-v', config['root'] + ':/project', '-v', str(BUNDLE / 'tools') + ':/setup:ro',
                    '--entrypoint', 'python', 'mcj-manager:' + __version__, '-c', seed,
                    input=json.dumps({'config': config, 'password': password}), text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not json.loads(result.stdout).get('initialized'):
        raise RuntimeError('initialization_failed')
    print('Vorbereitung abgeschlossen. Es wurden keine dauerhaften Container gestartet.')
    print('In UGOS Docker → Projekt erstellen → vorhandene Compose-Datei wählen: ' + str(compose))
    print('Projektname: ' + PROJECT + '. HTTPS-Proxy auf 127.0.0.1:8090 einrichten; RCON nie veröffentlichen.')
    print('Mit dem gewählten vorläufigen Passwort anmelden, Passwort ändern und E-Mail-Code oder Authenticator-App wählen.')
    print('Minecraft bleibt bis zur Sicherheitsabnahme lokal gebunden und durch die Whitelist gesperrt.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print('Vorbereitung gestoppt: ' + (str(error) if isinstance(error, (ValueError, RuntimeError))
                                         else type(error).__name__), file=sys.stderr)
        print('Vorhandene Daten nicht löschen. Bei einer begonnenen Vorbereitung den Ordner für die Diagnose erhalten.', file=sys.stderr)
        raise SystemExit(1)

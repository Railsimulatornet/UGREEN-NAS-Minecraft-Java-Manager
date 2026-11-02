"""Narrow Compose identity and safety checks shared by maintenance operations."""
from pathlib import PurePosixPath
from .project_paths import project_path
import re
import ipaddress
import subprocess


def compose_game_reference(approved_reference,image_id):
    match=re.fullmatch(r'itzg/minecraft-server:(java17|java21|java25)@sha256:[0-9a-f]{64}',approved_reference)
    if not match or not re.fullmatch(r'sha256:[0-9a-f]{64}',image_id):raise ValueError('untrusted_game_image')
    # UGOS cannot display repository/tag fields for a reference containing @sha256.
    # This is a local display alias; deployment still compares the full image ID.
    return 'itzg/minecraft-server:'+match[1]+'-mcj-'+image_id[7:19]


def verify_game_reference(reference,image_id):
    alias=re.fullmatch(r'itzg/minecraft-server:(?:java17|java21|java25)-mcj-([0-9a-f]{12})',reference)
    if alias and (not re.fullmatch(r'sha256:[0-9a-f]{64}',image_id) or alias[1]!=image_id[7:19]):
        raise RuntimeError('game_image_alias_mismatch')


def stop_container(container):
    """Tell Docker this is an intentional stop; never send SIGKILL after a deadline."""
    if not re.fullmatch('[0-9a-f]{64}',container.id):raise ValueError('container_identity_invalid')
    try:
        outcome=subprocess.run(['docker','container','stop','--timeout','-1',container.id],capture_output=True,timeout=600)
    except subprocess.TimeoutExpired:raise RuntimeError('shutdown_pending_no_forced_kill') from None
    if outcome.returncode:raise RuntimeError('container_stop_failed')
    container.reload()
    if container.status!='exited' or container.attrs['State']['ExitCode'] not in [0,143]:
        raise RuntimeError('unclean_server_shutdown')

def compose_identity(attributes,host_root,project):
    labels=attributes.get('Config',{}).get('Labels') or {}
    actual_project=labels.get('com.docker.compose.project')
    service=labels.get('com.docker.compose.service')
    compose=labels.get('com.docker.compose.project.config_files','')
    working=labels.get('com.docker.compose.project.working_dir')
    expected=PurePosixPath(host_root)/'docker-compose.yaml'
    if actual_project!=project or service!='minecraft' or compose!=str(expected) or working!=host_root:
        raise ValueError('compose_identity_mismatch')
    return ['docker','compose','-p',actual_project,'-f',compose],service

def validate_game_configuration(config,host_root,expected_name='mcj_minecraft',expected_host_port=25565,expected_host_ip='127.0.0.1',expected_voice_port=None):
    if set(config.get('services',{}))!={'manager','controller','minecraft'}:raise ValueError('compose_service_scope_mismatch')
    game=config['services']['minecraft']
    selected_user=config['services']['manager'].get('user','1009:10')
    if not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*',selected_user) or game.get('user')!=selected_user or game.get('privileged') or game.get('network_mode') in ['host','service:controller']:
        raise ValueError('unsafe_game_privileges')
    if game.get('container_name')!=expected_name or 'ALL' not in game.get('cap_drop',[]):raise ValueError('unsafe_game_container')
    if 'no-new-privileges:true' not in game.get('security_opt',[]):raise ValueError('unsafe_game_privileges')
    if not re.fullmatch(r'itzg/minecraft-server:(java17|java21|java25)(?:@sha256:[0-9a-f]{64}|-mcj-[0-9a-f]{12})?',game.get('image','')):
        raise ValueError('untrusted_game_image')
    ports=game.get('ports',[])
    try:address=ipaddress.ip_address(expected_host_ip)
    except ValueError:raise ValueError('unexpected_game_publication') from None
    if address.version!=4 or address.is_unspecified or address.is_multicast or address.is_link_local:
        raise ValueError('unexpected_game_publication')
    expected={('tcp',25565,str(expected_host_port))}
    if expected_voice_port is not None:
        if type(expected_voice_port) is not int or expected_voice_port!=24454:raise ValueError('unexpected_game_publication')
        expected.add(('udp',24454,'24454'))
    actual={(p.get('protocol'),int(p.get('target',0)),str(p.get('published'))) for p in ports}
    if len(ports)!=len(expected) or actual!=expected or any(p.get('host_ip')!=expected_host_ip for p in ports):
        raise ValueError('unexpected_game_publication')
    allowed={
        project_path(host_root,'server').as_posix():('/data',False),project_path(host_root,'control/runtime').as_posix():('/mcj',True),
        project_path(host_root,'control/roles').as_posix():('/mcj-control/roles',True),project_path(host_root,'control/reports').as_posix():('/mcj-control/reports',False),
        project_path(host_root,'secrets/rcon').as_posix():('/run/secrets/rcon',True)}
    mounts=game.get('volumes',[])
    if len(mounts)!=len(allowed):raise ValueError('unexpected_game_mount')
    for mount in mounts:
        if mount.get('type')!='bind' or mount.get('source') not in allowed:raise ValueError('unexpected_game_mount')
        if (mount.get('target'),bool(mount.get('read_only'))) != allowed[mount['source']]:raise ValueError('unsafe_game_mount')
    return game

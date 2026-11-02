import copy
from types import SimpleNamespace
import subprocess
import pytest
from mcj.infrastructure import compose_identity,validate_game_configuration,compose_game_reference,verify_game_reference

ROOT='/volume1/docker/minecraftjava'

def test_display_alias_rejects_unapproved_repositories_and_wrong_image_identity():
    image='sha256:'+'a'*64
    approved='itzg/minecraft-server:java25@sha256:'+'b'*64
    alias=compose_game_reference(approved,image)
    assert alias=='itzg/minecraft-server:java25-mcj-aaaaaaaaaaaa'
    verify_game_reference(alias,image)
    with pytest.raises(RuntimeError,match='game_image_alias_mismatch'):
        verify_game_reference(alias,'sha256:'+'c'*64)
    for reference in ['other/server:java25@sha256:'+'b'*64,'itzg/minecraft-server:latest',alias]:
        with pytest.raises(ValueError,match='untrusted_game_image'):compose_game_reference(reference,image)
    with pytest.raises(ValueError,match='untrusted_game_image'):compose_game_reference(approved,'not-an-image-id')

def test_display_alias_does_not_broaden_allowed_game_repository():
    config=configuration();config['services']['minecraft']['image']='itzg/minecraft-server:java25-mcj-'+'a'*12
    validate_game_configuration(config,ROOT)
    config['services']['minecraft']['image']='other/server:java25-mcj-'+'a'*12
    with pytest.raises(ValueError,match='untrusted_game_image'):validate_game_configuration(config,ROOT)
def configuration():
    return {'services':{'manager':{},'controller':{},'minecraft':{
        'user':'1009:10','container_name':'mcj_minecraft','cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
        'image':'itzg/minecraft-server:java25','ports':[{'target':25565,'published':'25565','host_ip':'127.0.0.1','protocol':'tcp'}],
        'volumes':[{'type':'bind','source':ROOT+'/'+source,'target':target,'read_only':read_only} for source,target,read_only in [
          ('server','/data',False),('control/runtime','/mcj',True),('control/roles','/mcj-control/roles',True),
          ('control/reports','/mcj-control/reports',False),('secrets/rcon','/run/secrets/rcon',True)]]}}}

def test_project_and_service_come_from_labels():
    attributes={'Config':{'Labels':{'com.docker.compose.project':'actual_ugos_name','com.docker.compose.service':'minecraft',
        'com.docker.compose.project.config_files':ROOT+'/docker-compose.yaml','com.docker.compose.project.working_dir':ROOT}}}
    prefix,service=compose_identity(attributes,ROOT,'actual_ugos_name')
    assert prefix==['docker','compose','-p','actual_ugos_name','-f',ROOT+'/docker-compose.yaml']
    assert service=='minecraft'
    with pytest.raises(ValueError):compose_identity(attributes,ROOT,'minecraftjava')

@pytest.mark.parametrize('mutation',[
 lambda game:game.update(user='0:0'),lambda game:game.update(privileged=True),lambda game:game.update(network_mode='host'),
 lambda game:game['ports'][0].update(host_ip='0.0.0.0'),lambda game:game['ports'][0].update(target=25575),
 lambda game:game.update(image='untrusted/image:latest'),lambda game:game['volumes'][0].update(source='/'),
 lambda game:game['volumes'][1].update(read_only=False),lambda game:game.update(cap_drop=[]),
])
def test_maintenance_refuses_scope_or_security_changes(mutation):
    config=configuration();mutation(config['services']['minecraft'])
    with pytest.raises(ValueError):validate_game_configuration(config,ROOT)

def test_expected_private_game_configuration_is_accepted():
    assert validate_game_configuration(configuration(),ROOT)['user']=='1009:10'

def test_explicit_binding_does_not_allow_maintenance_to_expand_network_access():
    config=configuration();config['services']['minecraft']['ports'][0]['host_ip']='192.168.1.50'
    with pytest.raises(ValueError,match='unexpected_game_publication'):validate_game_configuration(config,ROOT)
    validate_game_configuration(config,ROOT,expected_host_ip='192.168.1.50')
    for value in ['0.0.0.0','::','224.0.0.1','169.254.1.1','not-an-address']:
        config['services']['minecraft']['ports'][0]['host_ip']=value
        with pytest.raises(ValueError,match='unexpected_game_publication'):validate_game_configuration(config,ROOT,expected_host_ip=value)


def test_voice_udp_mapping_requires_explicit_infrastructure_configuration():
    config=configuration()
    config['services']['minecraft']['ports'].append({'target':24454,'published':'24454','host_ip':'127.0.0.1','protocol':'udp'})
    with pytest.raises(ValueError,match='unexpected_game_publication'):validate_game_configuration(config,ROOT)
    validate_game_configuration(config,ROOT,expected_voice_port=24454)
    for value in [True,25575,'24454',0]:
        with pytest.raises(ValueError,match='unexpected_game_publication'):validate_game_configuration(config,ROOT,expected_voice_port=value)
    for changed in [{'target':25575},{'published':'24455'},{'protocol':'tcp'},{'host_ip':'0.0.0.0'}]:
        candidate=copy.deepcopy(config);candidate['services']['minecraft']['ports'][1].update(changed)
        with pytest.raises(ValueError,match='unexpected_game_publication'):validate_game_configuration(candidate,ROOT,expected_voice_port=24454)
    config['services']['minecraft']['ports'].append({'target':25575,'published':'25575','host_ip':'127.0.0.1','protocol':'tcp'})
    with pytest.raises(ValueError,match='unexpected_game_publication'):validate_game_configuration(config,ROOT,expected_voice_port=24454)


def test_organized_mounts_are_validated_without_broadening_controller_scope(monkeypatch):
    from mcj.project_paths import project_path
    config=configuration()
    monkeypatch.setenv('MCJ_LAYOUT','services-v1')
    for mount in config['services']['minecraft']['volumes']:
        mount['source']=project_path(ROOT,mount['source'][len(ROOT)+1:]).as_posix()
    assert validate_game_configuration(config,ROOT)['volumes'][0]['source']==ROOT+'/mcj_minecraft/data'
    config['services']['minecraft']['volumes'][0]['source']=ROOT+'/manager/state'
    with pytest.raises(ValueError,match='unexpected_game_mount'):validate_game_configuration(config,ROOT)


def test_intentional_stop_disables_restart_without_force_kill(monkeypatch):
    from mcj.infrastructure import stop_container
    seen=[]
    container=SimpleNamespace(id='a'*64,status='exited',attrs={'State':{'ExitCode':0}},reload=lambda:None)
    def run(args,**kwargs):
        assert kwargs['timeout']==600
        seen.append(args);return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess,'run',run)
    stop_container(container)
    assert seen==[['docker','container','stop','--timeout','-1','a'*64]]
    def timeout(args,**kwargs):raise subprocess.TimeoutExpired(args,600)
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(RuntimeError,match='shutdown_pending_no_forced_kill'):stop_container(container)

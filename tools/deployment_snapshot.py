"""Compose definitions consumed privately, with canonical UGOS labels and no NAS binds."""
import json,os,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import install


ACTIONS={'config':['config','--format','json'],'check':['config','--quiet'],
         'start_game':['up','-d','controller','minecraft'],'start_manager':['up','-d','manager'],'down':['down']}


def invoke(image,root,definition,environment,action):
    if action not in ACTIONS:raise ValueError('setup_action_invalid')
    if not re.fullmatch(r'/volume[1-9][0-9]*/[A-Za-z0-9_/-]+',root) or '..' in Path(root).parts:raise ValueError('setup_path_invalid')
    if not re.fullmatch(r'(?:sha256:[0-9a-f]{64}|[a-z0-9._:/-]+@sha256:[0-9a-f]{64})',image):raise ValueError('setup_release_image_invalid')
    request=json.dumps({'project':install.PROJECT,'root':root,'definition':definition,'environment':environment,'action':action})
    return install.docker('run','--rm','-i','--network','none','--user','0:0','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges:true','--memory','512m','--pids-limit','64',
        '--tmpfs','/tmp:rw,nosuid,noexec,size=64m','--tmpfs',root+':rw,nosuid,noexec,size=4m,mode=0700',
        '-v','/var/run/docker.sock:/var/run/docker.sock','--entrypoint','python',image,
        '/opt/mcj/tools/deployment_snapshot.py',input=request,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def render(config,image,socket_gid):
    environment='MCJ_GAME_IMAGE='+install.GAME_IMAGE+'\nMCJ_GAME_MEMORY_MB='+str(config.get('container_memory_mb',8192))+'\n'
    value=invoke(image,config['root'],install.compose_text(config,socket_gid),environment,'config')
    return json.loads(value.stdout),environment


def main():
    raw=sys.stdin.buffer.read(262145)
    if len(raw)>262144:raise ValueError('setup_definition_too_large')
    value=json.loads(raw);root=Path(value['root']);project=value['project']
    if not isinstance(project,str) or not re.fullmatch('[a-z][a-z0-9_-]{1,63}',project):raise ValueError('setup_project_invalid')
    if value['action'] not in ACTIONS or not root.is_absolute() or '..' in root.parts:raise ValueError('setup_action_invalid')
    # This path is a fresh private container tmpfs, never a NAS parent bind.
    for name,content in [('docker-compose.yaml',value['definition']),('.env',value['environment'])]:
        fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(content)
    command=['docker','compose','-p',project,'--project-directory',str(root),'--env-file',str(root/'.env'),'-f',str(root/'docker-compose.yaml'),*ACTIONS[value['action']]]
    result=subprocess.run(command,cwd=root,env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp'},capture_output=True)
    if result.returncode:raise RuntimeError('setup_compose_failed')
    sys.stdout.buffer.write(result.stdout)


if __name__=='__main__':
    try:main()
    except Exception:
        print('setup_compose_failed',file=sys.stderr);raise SystemExit(1)

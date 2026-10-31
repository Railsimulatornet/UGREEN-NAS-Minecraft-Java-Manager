"""Private Compose runner: no NAS data mounts, includes, builds or image pulls."""
import json,os,re,subprocess,sys
from pathlib import Path

ACTIONS={'hash':['config','--hash','*'],
         'up':['up','-d','--no-deps','--no-build','--pull','never','manager','controller'],
         'stop':['stop','--timeout','30','manager','controller']}

def main():
    raw=sys.stdin.buffer.read(262145)
    if len(raw)>262144:raise ValueError('update_definition_limit')
    value=json.loads(raw);root=Path(value['root']);project=value['project'];definition=value['definition']
    if not re.fullmatch(r'/volume[1-9][0-9]*/[A-Za-z0-9_/-]+',str(root)) or '..' in root.parts:raise ValueError('update_root_invalid')
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{1,63}',project) or value['action'] not in ACTIONS:raise ValueError('update_scope_invalid')
    if set(definition)-{'name','services','networks'} or set(definition.get('services',{}))!={'manager','controller','minecraft'}:raise ValueError('update_definition_invalid')
    for name,content in [('docker-compose.yaml',json.dumps(definition)),('.env',value['environment'])]:
        fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(content)
    command=['docker','compose','-p',project,'--project-directory',str(root),'--env-file',str(root/'.env'),'-f',str(root/'docker-compose.yaml'),*ACTIONS[value['action']]]
    result=subprocess.run(command,cwd=root,env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp'},capture_output=True,timeout=120)
    if result.returncode:raise RuntimeError('update_compose_failed')
    if value['action']=='hash':sys.stdout.buffer.write(result.stdout)

if __name__=='__main__':
    try:main()
    except Exception:
        print('update_compose_failed',file=sys.stderr);raise SystemExit(1)

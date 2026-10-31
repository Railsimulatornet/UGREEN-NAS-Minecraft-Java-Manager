#!/usr/bin/env python3
"""Local NAS-owner recovery; never bypasses account authentication or MFA."""
import argparse,json,os,subprocess

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-address')
    parser.add_argument('--external-web',choices=['keep','local','allow'],default='keep')
    args=parser.parse_args()
    if os.name=='nt' or os.geteuid()!=0:raise RuntimeError('run_as_root_on_nas')
    inspected=json.loads(subprocess.check_output(['docker','inspect','mcj_manager'],text=True))[0]
    labels=inspected['Config'].get('Labels',{})
    if labels.get('com.docker.compose.project')!='ugreen_minecraft_java' or labels.get('com.docker.compose.service')!='manager' or not labels.get('com.docker.compose.project.config_files'):raise RuntimeError('compose_identity_mismatch')
    if not args.web_address and args.external_web=='keep':raise RuntimeError('no_access_change_requested')
    code="""
import json,os,sys
from pathlib import Path
from mcj.project_paths import project_path
from mcj.store import Store
from mcj import web_access
data=json.load(sys.stdin);root=Path(os.environ.get('PROJECT_ROOT','/project'))
st=Store(project_path(root,'state'),'/run/secrets/encryption')
current=web_access.settings(st,os.environ['APP_ORIGIN'])
target=web_access.address(data['address']) if data['address'] else current['address']
external=current['external_web'] if data['external']=='keep' else data['external']=='allow'
st.set('web_access',{'address':target,'external_web':external})
st.event('system','web_access_recovered',data={'external_web':external,'local_nas_owner':True})
print(json.dumps({'address':target,'external_web':external,'accounts_and_mfa_unchanged':True,'game_unchanged':True}))
"""
    result=subprocess.run(['docker','exec','-i',inspected['Id'],'python','-c',code],input=json.dumps({'address':args.web_address,'external':args.external_web}),text=True,capture_output=True)
    if result.returncode:raise RuntimeError('access_recovery_failed')
    print(result.stdout.strip())

if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:raise SystemExit(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__)

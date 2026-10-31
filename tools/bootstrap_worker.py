"""No listener: bounded installation worker, scoped by its immutable Docker launch context."""
import json,os,re,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cryptography.fernet import Fernet,InvalidToken
from mcj import bootstrap
import install,ugos_prepare,deployment_snapshot

def info(identifier):return json.loads(install.docker('inspect',identifier,stdout=subprocess.PIPE,text=True).stdout)[0]

def status(base,phase,**values):
    path=base/'status.json';previous=None
    if phase=='failed':
        try:previous=json.loads(bootstrap.read_regular(path)).get('progress')
        except (OSError,ValueError):pass
    bootstrap.atomic(path,json.dumps({'phase':phase,'updated':time.time(),'progress':bootstrap.step_progress(phase,previous),**values}).encode(),0o640,owner=(install.UID,install.GID))

def validate_context(context):
    own=info(os.environ['HOSTNAME']);labels=own['Config'].get('Labels') or {}
    if labels.get('mcj.purpose')!='first-install-preparation' or labels.get('mcj.setup.launcher')!=context['container']:raise ValueError('setup_worker_invalid')
    from browser_setup import launcher_context
    launcher=info(context['container']);address,parents=launcher_context(launcher)
    if own['Image']!=launcher['Image'] or address!=context['address'] or parents!=context['parents'] or context['base']!=parents[0]+'/mcj-einrichtung':raise ValueError('setup_context_invalid')
    config={'root':parents[0]+'/new','backup_root':parents[-1]+'/backups'}
    ugos_prepare.validate_mounts(config,own)
    return own

def port_check(context):
    ids=install.docker('ps','-q',stdout=subprocess.PIPE,text=True).stdout.split()
    if not ids:return
    for item in json.loads(install.docker('inspect',*ids,stdout=subprocess.PIPE,text=True).stdout):
        if item['Id']==context['container']:continue
        for bindings in (item['HostConfig'].get('PortBindings') or {}).values():
            for binding in bindings or []:
                if binding['HostPort'] in {'8090','25565'} and binding.get('HostIp') in {'','0.0.0.0','::',context['address']}:raise ValueError('setup_port_in_use')

def own_project(config,allow_empty=False):
    ids=install.docker('ps','-aq','--filter','label=com.docker.compose.project='+install.PROJECT,stdout=subprocess.PIPE,text=True).stdout.split()
    if not ids:return [] if allow_empty else None
    items=json.loads(install.docker('inspect',*ids,stdout=subprocess.PIPE,text=True).stdout)
    for item in items:
        labels=item['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.service') not in {'manager','controller','minecraft'} or labels.get('com.docker.compose.project.config_files')!=config['root']+'/docker-compose.yaml':raise ValueError('setup_project_identity_changed')
    return items

def wait_healthy(config,services,timeout=1200):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        items=own_project(config) or []
        chosen=[item for item in items if item['Config']['Labels'].get('com.docker.compose.service') in services]
        if len(chosen)==len(services) and all(item['State'].get('Health',{}).get('Status')=='healthy' for item in chosen):return
        if any(item['State']['Status'] in {'exited','dead'} for item in chosen):raise ValueError('setup_service_start_failed')
        time.sleep(3)
    raise ValueError('setup_service_start_timeout')

def main():
    context=json.loads(os.environ['MCJ_SETUP_CONTEXT']);validate_context(context)
    install.configure_identity(context['service_uid'],context['service_gid'])
    base=Path(context['base']);cipher=Fernet(bootstrap.read_regular(base/'queue.key',128));deadline=context['created']+14400
    while time.time()<deadline:
        request=base/'request.fernet';active=base/'active.fernet'
        if not request.exists():time.sleep(1);continue
        config=None;created=False;handover=False;trusted=None
        try:
            request.rename(active);raw=cipher.decrypt(bootstrap.read_regular(active,65536),ttl=1800)
            config,password=bootstrap.selection_config(json.loads(raw),context);raw=None
            validate_context(context);port_check(context);install.refuse_existing_project()
            result=ugos_prepare.prepare(config,password,base/'tls',lambda phase:status(base,phase),private_plan=True)
            password=None;created=True;compose=result['compose'];trusted=result['deployment_snapshot']
            def deploy(action):return deployment_snapshot.invoke(result['image'],config['root'],trusted['definition'],trusted['environment'],action)
            status(base,'starting');deploy('start_game')
            own_project(config);wait_healthy(config,{'controller','minecraft'})
            status(base,'handover');launcher=info(context['container'])
            if (launcher['Config'].get('Labels') or {}).get('mcj.purpose')!='browser-first-installation':raise ValueError('setup_launcher_identity_invalid')
            from browser_setup import stop_listener
            stop_listener(context)
            install.docker('stop','--time','10',context['container'],stdout=subprocess.PIPE,stderr=subprocess.PIPE);handover=True
            deploy('start_manager');wait_healthy(config,{'manager'},180)
            status(base,'complete',origin=context['origin'],project=install.PROJECT,compose=compose)
            # The new manager has its own copies. Remove setup-only credentials and private keys.
            for name in ['EINRICHTUNGSCODE.txt','queue.key','active.fernet','request.fernet']:
                path=base/name
                if path.exists() and not path.is_symlink():path.unlink()
            tls=base/'tls'
            if tls.is_dir() and not tls.is_symlink() and not any(path.is_symlink() for path in tls.rglob('*')):shutil.rmtree(tls)
            return
        except Exception as error:
            # Deliberately bounded codes; Docker output and request values can contain credentials.
            code=str(error) if isinstance(error,ValueError) and re.fullmatch(r'[a-z_]{3,80}',str(error)) else ('setup_preparation_failed' if not created else 'setup_failed_'+type(error).__name__.lower())
            if created and config and not handover:
                try:
                    items=own_project(config,allow_empty=True)
                    if items and trusted:deploy('down')
                except Exception:code='setup_cleanup_review_required'
            status(base,'failed',error=code)
            if active.exists() and not active.is_symlink():active.unlink()
            if handover:
                # Status remains readable in the NAS file manager; never restart a
                # privileged supervisor against an interrupted active installation.
                return
    status(base,'expired')

if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit(1)

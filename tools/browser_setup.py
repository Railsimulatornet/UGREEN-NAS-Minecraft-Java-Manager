"""UGOS first start: create local TLS, isolate worker, then drop all HTTP privileges."""
import hashlib,ipaddress,json,os,re,secrets,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import install,ugos_prepare
from mcj import bootstrap,local_tls
from cryptography.fernet import Fernet

def inspect(*args):return json.loads(install.docker(*args,stdout=subprocess.PIPE,text=True).stdout)

def launcher_context(own):
    if (own.get('Config',{}).get('Labels') or {}).get('mcj.purpose')!='browser-first-installation':raise ValueError('setup_launcher_identity_invalid')
    ports=own.get('HostConfig',{}).get('PortBindings',{})
    if set(ports)!={'8090/tcp'} or len(ports['8090/tcp'])!=1:raise ValueError('setup_private_binding_required')
    port=ports['8090/tcp'][0];address=bootstrap.private_ip(port.get('HostIp',''))
    if port.get('HostPort')!='8090':raise ValueError('setup_port_required')
    parents=[]
    for mount in own.get('Mounts',[]):
        source=mount.get('Source','')
        if source=='/var/run/docker.sock':continue
        if (mount.get('Type')!='bind' or not mount.get('RW') or source!=mount.get('Destination') or
            not re.fullmatch(r'/volume[1-9][0-9]*/[A-Za-z0-9_/-]+',source) or str(Path(source))!=source or
            '..' in Path(source).parts or any(path.is_symlink() for path in [Path(source),*Path(source).parents])):
            raise ValueError('setup_parent_invalid')
        if not Path(source).is_dir():raise ValueError('setup_parent_missing')
        parents.append(source)
    if not 1<=len(parents)<=10 or len(set(parents))!=len(parents):raise ValueError('setup_parent_invalid')
    return address,parents

def host_facts(image,address):
    # Read-only, short-lived host network inspection. No host PID namespace, mounts or listeners.
    script="""import ipaddress,json,socket,struct
address=ipaddress.ip_address(ADDRESS)
networks=[]
for line in open('/proc/net/route').read().splitlines()[1:]:
 p=line.split()
 if len(p)<8 or p[2]!='00000000' or p[1]=='00000000':continue
 destination=socket.inet_ntoa(struct.pack('<I',int(p[1],16)));mask=socket.inet_ntoa(struct.pack('<I',int(p[7],16)))
 network=ipaddress.ip_network(destination+'/'+mask)
 if address in network:networks.append(network)
memory={p[0].rstrip(':'):int(p[1]) for p in (line.split() for line in open('/proc/meminfo')) if len(p)>1 and p[1].isdigit()}
if not networks:raise ValueError('setup_network_not_detected')
print(json.dumps({'network':str(max(networks,key=lambda x:x.prefixlen)),'available_mb':memory['MemAvailable']//1024}))
""".replace('ADDRESS',repr(address))
    result=install.docker('run','--rm','--network','host','--user',str(install.UID)+':'+str(install.GID),'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','128m','--pids-limit','32','--entrypoint','python',image,'-c',script,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    facts=json.loads(result.stdout);network=ipaddress.ip_network(facts['network'])
    if not any(network.subnet_of(parent) for parent in bootstrap.PRIVATE):raise ValueError('setup_network_not_private')
    maximum=min(65536,((facts['available_mb']-2048)//1024)*1024)
    if maximum<4096:raise ValueError('setup_memory_insufficient')
    return dict(facts,maximum_memory_mb=maximum,recommended_memory_mb=min(8192,maximum))


def listener_name(context):return 'mcj_setup_web_'+context['container'][:12]


def stop_listener(context):
    identifiers=install.docker('ps','-aq','--filter','name=^/'+listener_name(context)+'$',stdout=subprocess.PIPE,text=True).stdout.split()
    for identifier in identifiers:
        item=inspect('inspect',identifier)[0];labels=item['Config'].get('Labels') or {}
        if labels.get('mcj.purpose')!='browser-first-listener' or labels.get('mcj.setup.launcher')!=context['container']:raise ValueError('setup_listener_identity_invalid')
        install.docker('rm','-f',identifier,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def listener_command(context,image):
    return ['run','-d','--rm','--name',listener_name(context),'--label','mcj.purpose=browser-first-listener',
        '--label','mcj.setup.launcher='+context['container'],'--label','com.docker.compose.project=',
        '--label','com.docker.compose.service=','--label','com.docker.compose.version=',
        '--network','container:'+context['container'],'--user',str(install.UID)+':'+str(install.GID),
        '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','256m','--pids-limit','64',
        '--tmpfs','/tmp:rw,nosuid,noexec,size=64m','-e','MCJ_SETUP_CONTEXT='+json.dumps(context),
        '-v',context['base']+':/setup','--entrypoint','python',image,'/opt/mcj/tools/browser_setup_web.py']


def refuse_interrupted_setup(base):
    """Preserve an interrupted job and report a bounded, actionable stop."""
    base=Path(base)
    if not (base/'active.fernet').exists():return
    report=base/'status.json'
    previous=json.loads(bootstrap.read_regular(report)) if report.exists() else {}
    owner=None
    if report.exists():
        attributes=report.stat();owner=(attributes.st_uid,attributes.st_gid)
    code='setup_interrupted_installation_review_required'
    bootstrap.atomic(report,json.dumps({'phase':'failed','error':code,'updated':time.time(),
        'progress':bootstrap.step_progress('failed',previous.get('progress'))}).encode(),0o640,owner)
    notice=('Einrichtung sicher angehalten / Setup stopped safely\n\n'
        'Eine laufende Einrichtung wurde unterbrochen. Vorhandene Ordner und Zugangsdaten wurden nicht erneut verwendet oder überschrieben.\n'
        'Prüfe in UGOS → Docker das neue Minecraft-Projekt und seine Protokolle sowie status.json in diesem Ordner. '
        'Starte keine zweite Installation über denselben Datenordnern. Bewahre die Dateien für eine gezielte Wiederaufnahme auf.\n\n'
        'A running setup was interrupted. Existing folders and credentials have not been reused or overwritten.\n'
        'In UGOS → Docker, inspect the new Minecraft project, its logs and status.json in this folder. '
        'Do not start a second installation over the same data folders. Keep the files for a controlled recovery.\n')
    bootstrap.atomic(base/'EINRICHTUNG-ANGEHALTEN.txt',notice.encode(),0o640,owner)
    raise ValueError(code)


def main():
    if os.geteuid()!=0:raise ValueError('setup_initial_permissions_required')
    own=inspect('inspect',os.environ['HOSTNAME'])[0];address,parents=launcher_context(own)
    reference=own['Config']['Image'];selected=inspect('image','inspect',own['Image'])[0]
    image=ugos_prepare.image_identity(reference,own,selected)
    base=Path(parents[0])/'mcj-einrichtung'
    if base.is_symlink():raise ValueError('setup_symlink_refused')
    refuse_interrupted_setup(base)
    # Stop a prior same-container listener before privileged queue/TLS writes.
    stop_listener({'container':own['Id'],'base':str(base)})
    if base.exists():
        if (base/'status.json').exists() and json.loads(bootstrap.read_regular(base/'status.json')).get('phase')=='complete':
            print('Einrichtung abgeschlossen. Öffne https://'+address+':8090/');return
        if (base/'launcher.json').exists():
            previous=json.loads(bootstrap.read_regular(base/'launcher.json'))
            if previous.get('parents')!=parents or previous.get('address')!=address or previous.get('base')!=str(base):raise ValueError('setup_folder_belongs_to_other_launcher')
            if previous.get('container')!=own['Id']:
                # UGOS replaces the container when an installer image is updated. Preserve its
                # local trust, but stop only the old worker tied to this exact setup marker.
                if not re.fullmatch('[0-9a-f]{64}',previous.get('container','')):raise ValueError('setup_launcher_identity_invalid')
                stop_listener(previous)
                identifiers=install.docker('ps','-aq','--filter','label=mcj.setup.launcher='+previous['container'],stdout=subprocess.PIPE,text=True).stdout.split()
                for identifier in identifiers:
                    old=inspect('inspect',identifier)[0]
                    if (old['Config'].get('Labels') or {}).get('mcj.purpose')!='first-install-preparation':raise ValueError('setup_worker_identity_invalid')
                    install.docker('rm','-f',identifier,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        else:raise ValueError('setup_existing_folder_refused')
    else:base.mkdir(mode=0o750)
    # Stop only our previous worker on a deliberate restart, never another Compose project.
    name='mcj_setup_worker_'+own['Id'][:12]
    found=install.docker('ps','-aq','--filter','name=^/'+name+'$',stdout=subprocess.PIPE,text=True).stdout.strip()
    if found:
        old=inspect('inspect',found)[0]
        if (old['Config'].get('Labels') or {}).get('mcj.setup.launcher')!=own['Id']:raise ValueError('setup_worker_identity_invalid')
        install.docker('rm','-f',found,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    refuse_interrupted_setup(base)
    previous=json.loads(bootstrap.read_regular(base/'launcher.json')) if (base/'launcher.json').exists() else {}
    pair=(previous['service_uid'],previous['service_gid']) if 'service_uid' in previous else None
    identity=install.select_identity(image,pair)
    facts=host_facts(image,address)
    if not (base/'tls/identity.json').exists():local_tls.create(base/'tls',address)
    elif local_tls.status(base/'tls')['address']!=address:raise ValueError('setup_address_changed')
    code=secrets.token_urlsafe(32);bootstrap.atomic(base/'queue.key',Fernet.generate_key())
    for filename in ['request.fernet']:
        if (base/filename).exists():(base/filename).unlink()
    bootstrap.atomic(base/'EINRICHTUNGSCODE.txt',('MCJ Manager – zeitlich begrenzter Einrichtungscode\n\n'+code+'\n\nÖffne https://'+address+':8090/ und füge diesen Code ein.\nDer Code gilt vier Stunden. Nicht weitergeben.\n').encode(),0o640)
    bootstrap.atomic(base/'Heimnetz-Zertifikat.crt',(base/'tls/authority.crt').read_bytes(),0o644)
    bootstrap.atomic(base/'ZERTIFIKAT-HINWEIS.txt',('Lokales HTTPS-Vertrauenszertifikat\n\nSHA-256: '+local_tls.status(base/'tls')['authority_fingerprint']+'\n\nImportiere ausschließlich Heimnetz-Zertifikat.crt auf deinen Geräten als vertrauenswürdige Zertifizierungsstelle.\nNiemals private Schlüssel importieren oder weitergeben. Anleitung: https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/blob/main/docs/HTTPS.md\n').encode(),0o644)
    context={'container':own['Id'],'image':image,'base':str(base),'parents':parents,'address':address,'origin':'https://'+address+':8090',
             'network':facts['network'],'maximum_memory_mb':facts['maximum_memory_mb'],'recommended_memory_mb':facts['recommended_memory_mb'],
             **identity,'created':time.time(),'code_hash':hashlib.sha256(code.encode()).hexdigest()}
    bootstrap.atomic(base/'launcher.json',json.dumps(context).encode())
    bootstrap.atomic(base/'status.json',b'{"phase":"ready"}')
    for path in [base,*base.rglob('*')]:
        if path.is_symlink():raise ValueError('setup_symlink_refused')
        os.chown(path,install.UID,install.GID)
    command=['run','-d','--rm','--name',name,'--label','mcj.purpose=first-install-preparation','--label','mcj.setup.launcher='+own['Id'],
        '--label','com.docker.compose.project=','--label','com.docker.compose.service=','--label','com.docker.compose.version=',
        '--network','none','--user','0:0','--read-only','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--cap-add','FOWNER',
        '--security-opt','no-new-privileges:true','--memory','512m','--pids-limit','64','--tmpfs','/tmp:rw,nosuid,noexec,size=128m',
        '-e','MCJ_SETUP_CONTEXT='+json.dumps(context),'-e','MCJ_RELEASE_IMAGE='+image,'-v','/var/run/docker.sock:/var/run/docker.sock']
    for parent in parents:command+=['-v',parent+':'+parent]
    command+=['--entrypoint','python',image,'/opt/mcj/tools/bootstrap_worker.py']
    install.docker(*command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    stop_listener(context)
    install.docker(*listener_command(context,image),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    # This supervisor has NAS/Docker authority but never accepts network requests.
    # The separate unprivileged listener shares only this network namespace and /setup.
    print('Einrichtungszugang bereit: '+context['origin']+' – Code und öffentliches Zertifikat im NAS-Dateimanager unter '+str(base))
    while True:time.sleep(60)

if __name__=='__main__':
    try:main()
    except Exception as error:
        if isinstance(error,ValueError) and str(error)=='setup_interrupted_installation_review_required':
            print('Unterbrochene Einrichtung sicher angehalten. Prüfe in UGOS die Protokolle des neuen Minecraft-Projekts und EINRICHTUNG-ANGEHALTEN.txt im Einrichtungsordner. Vorhandene Daten bleiben erhalten.',file=sys.stderr)
        else:print('Einrichtung angehalten. Prüfe in UGOS die private NAS-IP, Docker-Ordner, freien Arbeitsspeicher und den Einrichtungsbericht. Vorhandene Installationen bleiben erhalten.',file=sys.stderr)
        raise SystemExit(1)

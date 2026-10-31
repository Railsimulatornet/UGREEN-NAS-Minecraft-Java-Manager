"""One-shot UGOS GUI preparation from the exact prebuilt image; no web listener."""
import json,os,re,secrets,stat,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import install
from mcj import __version__

FIELDS={'MCJ_PROJECT_DIR':'root','MCJ_BACKUP_DIR':'backup_root','MCJ_WEB_ADDRESS':'origin',
        'MCJ_ADMIN_NAME':'username','MCJ_ADMIN_EMAIL':'email','MCJ_PROXY_IPS':'trusted_proxies',
        'MCJ_LOCAL_NETWORKS':'local_networks','MCJ_GAME_BIND_ADDRESS':'game_bind_address'}


def settings(environment):
    config={target:environment.get(source,'').strip() for source,target in FIELDS.items()}
    config['game_bind_address']=config['game_bind_address'] or '127.0.0.1'
    config['accept_eula']=environment.get('MCJ_ACCEPT_EULA','').lower()=='true'
    return install.validate(config)


def validate_mounts(config,attributes):
    """Only the two explicitly selected NAS parents may receive installation files."""
    mounts=attributes.get('Mounts',[])
    for key in ['root','backup_root']:
        parent=str(Path(config[key]).parent)
        matches=[m for m in mounts if m.get('Type')=='bind' and m.get('Source')==parent and m.get('Destination')==parent and m.get('RW')]
        if len(matches)!=1:raise RuntimeError('setup_parent_mount_mismatch')
    if attributes.get('HostConfig',{}).get('NetworkMode')!='none':raise RuntimeError('setup_network_isolation_required')


def image_identity(reference,own,selected):
    if not isinstance(reference,str) or len(reference)>240 or not re.fullmatch(r'[a-z0-9][a-z0-9._/:@-]+',reference):
        raise ValueError('setup_release_image_invalid')
    if own.get('Image')!=selected.get('Id') or not re.fullmatch(r'sha256:[0-9a-f]{64}',selected.get('Id','')):
        raise RuntimeError('setup_release_image_mismatch')
    labels=selected.get('Config',{}).get('Labels') or {}
    if labels.get('org.opencontainers.image.version')!=__version__ or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})',labels.get('org.opencontainers.image.revision','')):
        raise RuntimeError('setup_release_image_unverified')
    # Use the exact image already downloaded by UGOS; no floating tag on the new installation.
    digests=selected.get('RepoDigests') or []
    repository=reference.split('@')[0].rsplit(':',1)[0] if ':' in reference.split('/')[-1] else reference.split('@')[0]
    wanted=[value for value in digests if value.split('@')[0] in {repository,'docker.io/'+repository} and re.fullmatch(r'.+@sha256:[0-9a-f]{64}',value)]
    return wanted[0] if len(wanted)==1 else selected['Id']


def configure_prebuilt(compose,config,image,tls_source=None,rendered=None):
    prefix=['compose','-p',install.PROJECT,'-f',str(compose)]
    data=rendered if rendered is not None else json.loads(install.docker(*prefix,'config','--format','json',stdout=subprocess.PIPE,text=True).stdout)
    for service in ['manager','controller']:
        data['services'][service].pop('build',None)
        data['services'][service]['image']=image
        data['services'][service]['pull_policy']='never'
    # Keep the two selections dynamic: maintenance changes these via .env.
    data['services']['minecraft']['image']='${MCJ_GAME_IMAGE:-'+install.GAME_IMAGE+'}'
    data['services']['minecraft']['mem_limit']='${MCJ_GAME_MEMORY_MB:-8192}m'
    if config.get('tls_mode')=='selfsigned':
        from mcj import local_tls
        import shutil
        base=Path(config['root'])/'manager/tls'
        if tls_source:
            source=Path(tls_source)
            if source.is_symlink() or any(p.is_symlink() for p in source.rglob('*')):raise RuntimeError('setup_symlink_refused')
            shutil.copytree(source,base)
        else:local_tls.create(base,config['nas_ip'])
        local_tls.status(base)
        for path in [base,*base.rglob('*')]:os.chown(path,install.UID,install.GID)
        manager=data['services']['manager'];manager['command']=['python','-m','mcj.launch']
        manager['environment'].update(MCJ_TLS_MODE='selfsigned',MCJ_TLS_DIR='/run/mcj-tls')
        manager['volumes'].append({'type':'bind','source':str(base),'target':'/run/mcj-tls','read_only':False})
        for port in manager['ports']:port['host_ip']=config['nas_ip']
        host=config['origin'].split('://',1)[1]
        manager['healthcheck']['test']=['CMD','python','-c',"import ssl,urllib.request;urllib.request.urlopen(urllib.request.Request('https://127.0.0.1:8090/healthz',headers={'Host':"+repr(host)+"}),context=ssl.create_default_context(cafile='/run/mcj-tls/authority.crt'),timeout=5).read()"]
    compose.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.chown(compose,install.UID,install.GID);compose.chmod(0o640)
    if rendered is None:install.docker(*prefix,'config','--quiet')
    return data


def first_login_file(root,config,password):
    """Private one-time credential. Never include its contents in logs or reports."""
    path=Path(root)/'manager/state/ERSTE-ANMELDUNG.txt'
    text=('MCJ Manager – erste Anmeldung\n\nWebadresse: '+config['origin']+'\nBenutzer: '+config['username']+'\nVorläufiges Passwort: '+password+'\n\n'
          'Öffne die Webadresse. Ändere dieses Passwort bei der ersten Anmeldung und wähle einen E-Mail-Sicherheitscode oder eine Authenticator-App.\n'
          'Open the web address, change this password at first sign-in, and choose an email security code or an authenticator app.\n'
          'Diese Datei wird nach dem ersten Passwortwechsel automatisch entfernt. Gib sie nicht weiter.\n')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(text)
    os.chown(path,install.UID,install.GID)
    return path


def prepare(config_override=None,initial_password=None,tls_source=None,progress=None,private_plan=False):
    if os.name=='nt' or os.geteuid()!=0:raise RuntimeError('setup_root_container_required')
    if config_override is None:config=settings(os.environ)
    else:
        base_keys=set(FIELDS.values())|{'accept_eula'}
        config=install.validate({k:v for k,v in config_override.items() if k in base_keys})
        config.update({k:v for k,v in config_override.items() if k in {'tls_mode','access_mode','nas_ip','container_memory_mb','public_game'}})
        if config.get('tls_mode','proxy') not in {'selfsigned','proxy'}:raise ValueError('setup_fields_invalid')
        if config.get('access_mode','internal') not in {'internal','external'}:raise ValueError('setup_fields_invalid')
        if 'container_memory_mb' in config and (type(config['container_memory_mb']) is not int or not 4096<=config['container_memory_mb']<=65536 or config['container_memory_mb']%1024):raise ValueError('setup_fields_invalid')
    def phase(value):
        if progress:progress(value)
    password=initial_password if initial_password is not None else secrets.token_urlsafe(24)
    if not isinstance(password,str) or not 12<=len(password)<=128:raise ValueError('initial_password_invalid')
    identifier=os.environ.get('HOSTNAME','')
    if not re.fullmatch(r'[0-9a-f]{12,64}',identifier):raise RuntimeError('setup_container_identity_missing')
    own=json.loads(install.docker('inspect',identifier,stdout=subprocess.PIPE,text=True).stdout)[0]
    if (own.get('Config',{}).get('Labels') or {}).get('mcj.purpose')!='first-install-preparation':
        raise RuntimeError('setup_container_label_missing')
    validate_mounts(config,own)
    reference=os.environ.get('MCJ_RELEASE_IMAGE','')
    selected=json.loads(install.docker('image','inspect',reference,stdout=subprocess.PIPE,text=True).stdout)[0]
    image=image_identity(reference,own,selected)
    if config_override is None:
        # The legacy direct launcher must not silently use the template's NAS identity.
        install.select_identity(image)
    phase('checking');guard,raw=install.preflight(config,check_ports=False)
    phase('folders');socket_gid=os.stat('/var/run/docker.sock').st_gid
    trusted=None
    if private_plan:
        import deployment_snapshot
        trusted,environment=deployment_snapshot.render(config,image,socket_gid)
    compose=install.prepare(config,guard,raw,socket_gid)
    if 'container_memory_mb' in config:
        with (Path(config['root'])/'.env').open('a',encoding='utf-8') as stream:stream.write('MCJ_GAME_MEMORY_MB='+str(config['container_memory_mb'])+'\n')
    configured=configure_prebuilt(compose,config,image,tls_source,trusted)
    if private_plan:
        definition=json.dumps(configured,ensure_ascii=False)
        deployment_snapshot.invoke(image,config['root'],definition,environment,'check')
    install.refuse_existing_project()
    phase('runtime');install.docker('pull',install.GAME_IMAGE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    phase('account')
    seed="import sys;sys.path.insert(0,'/opt/mcj/tools');from initialize_installation import initialize;import json;value=json.load(sys.stdin);print(json.dumps(initialize('/project',value['config'],value['password'])))"
    seed_config={**config,'initial_password_chosen':initial_password is not None}
    result=install.docker('run','--rm','-i','--log-driver','none','--network','none','--user',str(install.UID)+':'+str(install.GID),'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,noexec,size=64m','-v',config['root']+':/project','--entrypoint','python',image,'-c',seed,input=json.dumps({'config':seed_config,'password':password}),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if not json.loads(result.stdout).get('initialized'):raise RuntimeError('initialization_failed')
    if initial_password is None:first_login_file(config['root'],config,password)
    sys.path.insert(0,str(install.BUNDLE))
    from mcj.store import Store
    st=Store(Path(config['root'])/'manager/state',Path(config['root'])/'manager/secrets/encryption')
    with st.db() as db:uid=db.execute('SELECT id FROM users WHERE username=?',(config['username'],)).fetchone()[0]
    st.set('gui_bootstrap',{'user_id':uid,'credential_file_removed':initial_password is not None})
    st.set('web_access',{'address':config['origin'],'external_web':config.get('access_mode')=='external'})
    policy={'public_game':config.get('public_game') is True}
    policy_file=Path(config['root'])/'mcj_controller/control/roles/network-access.json'
    Store.atomic(policy_file,json.dumps(policy).encode(),0o640);os.chown(policy_file,install.UID,install.GID)
    for path in [Path(config['root'])/'manager/state',*(Path(config['root'])/'manager/state').iterdir()]:
        if path.is_symlink():raise RuntimeError('setup_symlink_refused')
        os.chown(path,install.UID,install.GID)
    instructions=('Vorbereitung abgeschlossen.\n\n1. In UGOS Docker ein neues Projekt mit der Datei '+str(compose)+' erstellen.\n'
                  '2. Als Projektnamen '+install.PROJECT+' verwenden und starten.\n'
                  '3. Den HTTPS-Zugang gemäß Anleitung auf 127.0.0.1:8090 einrichten.\n'
                  '4. Erste Zugangsdaten: manager/state/ERSTE-ANMELDUNG.txt.\n'
                  '5. Im Browser anmelden. Passwort ändern, E-Mail-Code oder Authenticator-App wählen und dem Assistenten folgen. / Sign in, change the password, choose email codes or an authenticator app, and follow the wizard.\n'
                  'Das Vorbereitungsprojekt kann anschließend gestoppt bleiben. Vorhandene Projekte wurden nicht verändert.\n')
    if private_plan:
        instructions=('MCJ Manager – Browser-Einrichtung\n\n'
                      'Nach Abschluss öffnet sich der Manager unter '+config['origin']+'.\n'
                      'Der Minecraft-Datenordner ist bereits eingerichtet. Diesen Ordner niemals als neues UGOS-Projekt importieren: UGOS kann dabei seine Dateirechte ändern.\n'
                      'Für spätere Aktualisierungen das bestehende UGOS-Einrichtungsprojekt mit der Aktualisierungsvorlage verwenden. Anleitung: Einstellungen → Manager aktualisieren.\n')
    target=Path(config['root'])/'START-HIER.txt';target.write_text(instructions,encoding='utf-8');target.chmod(0o640);os.chown(target,install.UID,install.GID)
    print('Vorbereitung abgeschlossen. Öffne START-HIER.txt im neuen Projektordner. Keine dauerhaften Server gestartet; keine Passwörter im Protokoll.')
    result={'compose':str(compose),'origin':config['origin'],'image':image,'project':install.PROJECT}
    if private_plan:result['deployment_snapshot']={'definition':definition,'environment':environment}
    return result


if __name__=='__main__':
    try:prepare()
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError):
        # Docker exceptions and configuration values may contain secrets; do not print them.
        print('Vorbereitung gestoppt. Prüfe Image, Pflichtangaben, EULA-Zustimmung, Ordnerfreigaben und vorhandene Installationen anhand der Anleitung. Angelegte Dateien zur Diagnose behalten; keinen bestehenden Ordner löschen.',file=sys.stderr)
        raise SystemExit(1)

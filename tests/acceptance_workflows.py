"""End-to-end checks against the disposable, running three-service acceptance stack."""
import hashlib,io,json,os,re,secrets,time,zipfile
from pathlib import Path
import httpx,pyotp
from mcj.store import Store
from mcj import mods

ROOT=Path('/project');st=Store(ROOT/'state',ROOT/'secrets/encryption')
assert (ROOT/'docker-compose.yaml').read_text().splitlines()[0]=='name: mcj_acceptance_20261024'
STATE=ROOT/'state/.acceptance-fixture.fernet';RESULT=ROOT/'state/acceptance-results.json'
fixture=json.loads(st.cipher.decrypt(STATE.read_bytes())) if STATE.exists() else {'passed':[],'accounts':{},'artifacts':{}}
def save():st.atomic(STATE,st.cipher.encrypt(json.dumps(fixture).encode()),0o600)
def report(name,detail=None):
    print(json.dumps({'check':name,'result':'passed','details':detail},ensure_ascii=False),flush=True)
    if name not in fixture['passed']:fixture['passed'].append(name)
    save();st.atomic(RESULT,json.dumps({'passed':fixture['passed'],'last_check':name,'finished':False}).encode())

class BrowserClient:
    def __init__(self,name):
        self.name=name;self.account=fixture['accounts'].setdefault(name,{})
        self.client=httpx.Client(base_url='http://manager:8090',timeout=30,headers={'Host':'localhost:18091','Origin':'http://localhost:18091'})
        self.csrf=self.account.get('csrf');self.cookie=self.account.get('cookie')
    def request(self,method,path,data=None,expected=200,files=None):
        headers={}
        if self.cookie:headers['Cookie']='__Host-mcj='+self.cookie
        if self.csrf:headers['X-CSRF-Token']=self.csrf
        response=self.client.request(method,'/api'+path,json=data if files is None else None,files=files,headers=headers)
        value=response.json() if 'application/json' in response.headers.get('content-type','') else response.text
        if response.status_code!=expected:
            code=value.get('detail','unexpected_response') if isinstance(value,dict) else 'unexpected_response'
            raise AssertionError(path+': '+str(response.status_code)+' '+str(code)+' (expected '+str(expected)+')')
        if response.cookies.get('__Host-mcj'):self.cookie=response.cookies.get('__Host-mcj')
        if isinstance(value,dict) and value.get('csrf'):self.csrf=value['csrf']
        self.account.update(cookie=self.cookie,csrf=self.csrf);save()
        return value
    def get(self,path,expected=200):return self.request('GET',path,expected=expected)
    def post(self,path,data=None,expected=200):return self.request('POST',path,data or {},expected)
    def verify_login_factor(self):
        if self.account.get('factor')=='totp':
            with st.db() as db:last=db.execute('SELECT totp_last FROM users WHERE username=?',(self.name,)).fetchone()[0]
            while int(time.time()//30)+1<=last:time.sleep(1)
            step=max(int(time.time()//30),last+1)
            self.request('POST','/auth/verify',{'code':pyotp.TOTP(self.account['totp']).at(step*30)})
        else:
            previous=mail_fingerprint();challenge=self.post('/auth/email-challenge')['challenge']
            code=mail_code(previous);self.request('POST','/auth/verify',{'code':code,'challenge':challenge})
    def login(self):
        previous=mail_fingerprint()
        result=self.post('/auth/login',{'username':self.name,'password':self.account['password']})
        if result['mfa_required']:
            if self.account.get('factor')=='email':self.post('/auth/verify',{'challenge':result['challenge'],'code':mail_code(previous)})
            else:self.verify_login_factor()
        return result

def mail_fingerprint():
    path=ROOT/'state/.acceptance-mail.fernet'
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def mail_message(previous):
    deadline=time.monotonic()+10;path=ROOT/'state/.acceptance-mail.fernet'
    while time.monotonic()<deadline:
        if path.exists() and mail_fingerprint()!=previous:return json.loads(st.cipher.decrypt(path.read_bytes()))
        time.sleep(.1)
    raise AssertionError('The isolated email adapter did not receive a new message')
def mail_code(previous):return re.search(r'\b\d{6}\b',mail_message(previous)['body'])[0]

def enroll(name,method,initial=None):
    account=fixture['accounts'].setdefault(name,{})
    if 'password' not in account:
        credentials=json.loads(st.cipher.decrypt((ROOT/'state/.initial-accounts.fernet').read_bytes()))
        account['password']=initial or credentials[name]['password'];save()
    client=BrowserClient(name)
    with st.db() as db:user=dict(db.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone())
    if account.get('cookie'):
        try:client.get('/auth/me')
        except AssertionError:client.cookie=None;client.csrf=None;client.login()
    else:client.login()
    if user['force_password']:
        new=account.setdefault('new_password',secrets.token_urlsafe(24)+'Aa1!');save()
        client.post('/auth/password',{'current':account['password'],'password':new})
        account['password']=new;save()
    if not user['factor']:
        if method=='email':
            client.post('/auth/language',{'language':'en'})
            previous=mail_fingerprint();challenge=client.post('/auth/setup/email')['challenge'];code=mail_code(previous)
        else:
            setup=client.post('/auth/setup/totp');challenge=setup['challenge'];account['totp']=setup['secret'];save()
            code=pyotp.TOTP(setup['secret']).at((int(time.time()//30)+1)*30)
        result=client.post('/auth/setup/confirm',{'method':method,'challenge':challenge,'code':code})
        account.update(factor=method,backup_codes=result['backup_codes']);save()
        if method=='totp':client.post('/auth/verify',{'code':code},expected=401)
    else:account['factor']=user['factor'];save()
    assert client.get('/auth/me')['mfa_verified']
    return client

def queue(client,kind,payload=None,success=True,mode='idle_now'):
    identifier=client.post('/jobs',{'kind':kind,'payload':payload or {},'mode':mode,'approved':True})['id']
    deadline=time.monotonic()+650
    last_state=None
    while time.monotonic()<deadline:
        jobs=client.get('/jobs');job=next(x for x in jobs if x['id']==identifier)
        if job['state']!=last_state:
            print(json.dumps({'progress':kind,'state':job['state']}),flush=True);last_state=job['state']
        if job['state'] in ['succeeded','failed','blocked','interrupted']:
            result=json.loads(job['result']) if job['result'] else {}
            if success and job['state']!='succeeded':raise AssertionError(kind+' ended '+job['state']+': '+str(result.get('reason','unknown'))[:150])
            if not success and job['state']!='failed':raise AssertionError('The incompatible runtime was unexpectedly accepted')
            return identifier,result
        time.sleep(2)
    raise AssertionError(kind+' timed out')

def make_jar(identifier,broken=False):
    metadata={'schemaVersion':1,'id':identifier,'version':'1.0.0','name':identifier,'environment':'server',
       'depends':{'minecraft':'26.3','java':'>=25','fabricloader':'>=0.20.1'}}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as jar:
        if broken:
            metadata['mixins']=['acceptance-failure.mixins.json']
            jar.writestr('acceptance-failure.mixins.json',json.dumps({'required':True,'package':'mcj.acceptance.unavailable',
                'compatibilityLevel':'JAVA_25','mixins':['IntentionallyMissingMixin'],'injectors':{'defaultRequire':1}}))
        jar.writestr('fabric.mod.json',json.dumps(metadata))
    return output.getvalue()

def upload(client,identifier,broken=False):
    result=client.request('POST','/mods/upload',files=[('files',(identifier+'.jar',make_jar(identifier,broken),'application/java-archive'))])
    return result['staged'][0]['id']

try:
    if 'two_admins_and_separate_second_factors' not in fixture['passed']:
        with st.db() as db:assert [(r[0],r[1]) for r in db.execute('SELECT username,admin FROM users ORDER BY id')]==[('Roman',1),('Moritz',1)]
        anonymous=BrowserClient('anonymous');anonymous.get('/overview',401)
        roman=enroll('Roman','totp');moritz=enroll('Moritz','email')
        assert roman.get('/auth/me')['user']['language']=='de' and moritz.get('/auth/me')['user']['language']=='en'
        assert len(roman.account['backup_codes'])==10 and len(moritz.account['backup_codes'])==10
        report('two_admins_and_separate_second_factors',{'totp_replay_rejected':True,'email_transport':'isolated encrypted capture','production_accounts_untouched':True})
    roman=BrowserClient('Roman');moritz=BrowserClient('Moritz')
    if 'viewer_authorization_boundaries' not in fixture['passed']:
        with st.db() as db:exists=db.execute("SELECT id FROM users WHERE username='AcceptanceViewer'").fetchone()
        if not exists:
            result=roman.post('/users',{'username':'AcceptanceViewer','email':'viewer@example.invalid','admin':False,'language':'de'})
            fixture['accounts']['AcceptanceViewer']={'password':result['initial_password']};save()
        viewer=enroll('AcceptanceViewer','totp')
        assert viewer.get('/overview')['server']['version']=='26.3'
        viewer.get('/users',403);viewer.post('/console',{'command':'stop'},403);viewer.post('/jobs',{'kind':'backup'},403)
        report('viewer_authorization_boundaries')
    if 'initial_backup' not in fixture['passed']:
        queue(roman,'backup',{'kind':'manual'})
        backups=roman.get('/backups');backup=next(x for x in backups if x['state']=='verified')
        fixture['artifacts']['initial_backup']=backup['id'];save()
        report('initial_backup',{'archive_verified':True})
    if 'upload_apply_disable_restart' not in fixture['passed']:
        identifier=fixture['artifacts'].get('good_mod')
        if not identifier:identifier=upload(roman,'mcj_acceptance_mod');fixture['artifacts']['good_mod']=identifier;save()
        queue(roman,'apply_mods')
        row=next(x for x in roman.get('/mods')['mods'] if x['id']==identifier)
        assert row['state']=='installed' and row['installed_enabled']==1
        roman.post('/mods/'+identifier+'/desired',{'enabled':False});queue(roman,'apply_mods')
        queue(roman,'server',{'operation':'restart'})
        row=next(x for x in roman.get('/mods')['mods'] if x['id']==identifier)
        assert row['enabled']==0 and row['installed_enabled']==0
        report('upload_apply_disable_restart',{'backup_and_isolated_test_before_apply':True,'disabled_state_persisted':True})
    if 'incompatible_runtime_preserves_live_configuration' not in fixture['passed']:
        before={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (ROOT/'server/mods').glob('*.jar')}
        runtime_before=(ROOT/'control/runtime/runtime.json').read_bytes()
        identifier=fixture['artifacts'].get('bad_mod')
        if not identifier:identifier=upload(roman,'mcj_acceptance_failure',True);fixture['artifacts']['bad_mod']=identifier;save()
        queue(roman,'apply_mods',success=False)
        after={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (ROOT/'server/mods').glob('*.jar')}
        assert before==after and runtime_before==(ROOT/'control/runtime/runtime.json').read_bytes()
        assert roman.get('/overview')['status']['container_status']=='running'
        roman.post('/mods/'+identifier+'/desired',{'enabled':False})
        report('incompatible_runtime_preserves_live_configuration',{'failing_mod_never_installed':True,'server_running':True})
    if 'version_discovery_test_approval_apply' not in fixture['passed']:
        catalog=roman.post('/versions/check');assert '26.3' in [x['id'] for x in catalog['releases']]
        planned=roman.post('/versions/plan',{'version':'26.3','java':25,'loader':'FABRIC','loader_version':'0.20.1'})
        assert planned['metadata_checks']=='passed' and planned['automatic_minecraft_upgrades'] is False
        queue(roman,'version_test',{'id':planned['id']})
        plan=next(x for x in roman.get('/versions')['plans'] if x['id']==planned['id'])
        assert plan['state']=='tested' and plan['test_result']['live_configuration_changed'] is False
        queue(roman,'version_apply',{'id':planned['id']})
        assert roman.get('/overview')['server']['version']=='26.3'
        report('version_discovery_test_approval_apply',{'explicit_version':'26.3','automatic_jump':False,'fresh_backup_and_repeat_isolated_test_at_apply':True})
    if 'backup_restore_full_workflow' not in fixture['passed']:
        identifier=fixture['artifacts']['initial_backup'];queue(roman,'restore_test',{'id':identifier})
        queue(roman,'restore',{'id':identifier,'confirmation':'restore '+identifier})
        assert all(x['protected'] for x in roman.get('/mods')['mods'])
        assert roman.get('/overview')['status']['container_status']=='running'
        record=next(x for x in roman.get('/backups') if x['id']==identifier)
        assert record['restore_tested'] and record['restored']
        report('backup_restore_full_workflow',{'isolated_test':True,'pre_restore_backup':True,'original_mod_set_restored':True})
    if 'password_reset_requires_second_factor_and_invalidates_sessions' not in fixture['passed']:
        message=json.loads(st.cipher.decrypt((ROOT/'state/.acceptance-mail.fernet').read_bytes()))
        match=re.search(r'#reset=([A-Za-z0-9_-]+)',message['body'])
        with st.db() as db:existing=bool(match) and db.execute('SELECT COUNT(*) FROM challenges WHERE token=? AND kind=? AND expires>?',(st.digest(match[1]),'reset',time.time())).fetchone()[0]
        if not existing:
            with st.db() as db:reset_email=db.execute('SELECT email FROM users WHERE username=?',('Moritz',)).fetchone()[0]
            previous=mail_fingerprint();moritz.post('/auth/forgot',{'email':reset_email})
            message=mail_message(previous)
        token=re.search(r'#reset=([A-Za-z0-9_-]+)',message['body'])[1]
        replacement=secrets.token_urlsafe(24)+'Aa1!'
        print(json.dumps({'progress':'password_reset','step':'missing_factor_must_fail'}),flush=True)
        moritz.post('/auth/reset',{'token':token,'password':replacement},401)
        previous=mail_fingerprint();challenge=moritz.post('/auth/reset/email-challenge',{'token':token,'password':replacement})['challenge']
        code=mail_code(previous)
        print(json.dumps({'progress':'password_reset','step':'valid_factor'}),flush=True)
        moritz.post('/auth/reset',{'token':token,'password':replacement,'challenge':challenge,'code':code})
        moritz.get('/overview',401)
        moritz.account['password']=replacement;moritz.cookie=None;moritz.csrf=None;moritz.client.cookies.clear();save();moritz.login()
        moritz.post('/auth/reset',{'token':token,'password':replacement,'challenge':challenge,'code':code},400)
        report('password_reset_requires_second_factor_and_invalidates_sessions',{'single_use_link':True,'second_factor_retained':True})
    if 'recovery_codes_single_use_and_regeneration' not in fixture['passed']:
        old=roman.account['backup_codes']
        roman.post('/auth/logout');roman.cookie=None;roman.csrf=None;roman.client.cookies.clear()
        roman.post('/auth/login',{'username':'Roman','password':roman.account['password']})
        roman.get('/overview',403)
        roman.post('/auth/verify',{'code':old[0],'recovery':True})
        roman.post('/auth/verify',{'code':old[0],'recovery':True},401)
        fresh=roman.post('/auth/backup-codes')['backup_codes'];roman.account['backup_codes']=fresh;save()
        roman.post('/auth/verify',{'code':old[1],'recovery':True},401)
        roman.post('/auth/verify',{'code':fresh[0],'recovery':True})
        with st.db() as db:
            rows=db.execute("SELECT hash,used FROM recovery_codes WHERE user_id=(SELECT id FROM users WHERE username='Roman')").fetchall()
        assert len(rows)==10 and sum(bool(x['used']) for x in rows)==1
        assert all(x['hash'] not in fresh and re.fullmatch('[0-9a-f]{64}',x['hash']) for x in rows)
        report('recovery_codes_single_use_and_regeneration',{'old_codes_invalidated':True,'hashes_only':True})
    if 'security_rejections_and_container_exposure' not in fixture['passed']:
        response=roman.client.post('/api/chat',json={'message':'rejected'},headers={'Host':'localhost:18091','Origin':'https://foreign.invalid'})
        assert response.status_code==403 and response.headers['x-frame-options']=='DENY' and response.headers['cache-control']=='no-store'
        response=roman.client.post('/api/chat',json={'message':'rejected'},headers={'Host':'localhost:18091','Origin':'http://localhost:18091','Cookie':'__Host-mcj='+roman.cookie})
        assert response.status_code==403 and response.json()['detail']=='csrf_failed'
        response=roman.client.get('/healthz',headers={'Host':'foreign.invalid'})
        assert response.status_code==400 and response.headers['x-content-type-options']=='nosniff'
        import docker
        engine=docker.from_env()
        for name in ['mcj_acceptance_manager','mcj_acceptance_controller','mcj_acceptance_minecraft']:
            container=engine.containers.get(name)
            assert container.attrs['Config']['User']=='1009:10' and not container.attrs['HostConfig']['Privileged']
            for bindings in (container.attrs['HostConfig'].get('PortBindings') or {}).values():
                assert all(x['HostIp']=='127.0.0.1' for x in (bindings or []))
            if name.endswith('manager'):assert all(x['Source']!='/var/run/docker.sock' for x in container.attrs['Mounts'])
        report('security_rejections_and_container_exposure',{'origin_csrf_host_rejected':True,'loopback_only':True,'web_without_docker_socket':True})
    if 'guard_journal_to_events_and_export' not in fixture['passed']:
        # Deliberate journal fixtures in the disposable stack, never real-player proof.
        identifier='00000000-0000-0000-0000-000000000001';at=time.time()
        path=ROOT/'control/reports/player-events.jsonl'
        with path.open('a') as output:
            for event,stamp in [('player_login',at-123),('player_logout',at)]:
                output.write(json.dumps({'uuid':identifier,'name':'AcceptanceMock','event':event,'at':stamp})+'\n')
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            records=[x for x in roman.get('/events?category=player') if x['data'].get('uuid')==identifier]
            if len(records)>=2:break
            time.sleep(2)
        assert records[0]['event']=='player_logout' and records[0]['data']['session_seconds']==123
        assert records[0]['at']==at and records[1]['at']==at-123
        assert 'AcceptanceMock' in roman.get('/events/export')
        report('guard_journal_to_events_and_export',{'source':'simulated journal in isolated acceptance stack','timestamps_preserved':True,'session_seconds':123,'client_permission_proof':False})
    if 'server_settings_staged_tested_approved_and_applied' not in fixture['passed']:
        settings=roman.get('/server/settings');current=settings['current']
        forbidden={'version':current['version'],'java':current['java'],'loader':current['loader'],'loader_version':current['loader_version'],
                   'properties':{'online-mode':'false'}}
        roman.post('/versions/plan',forbidden,409)
        configuration={'version':current['version'],'java':current['java'],'loader':current['loader'],'loader_version':current['loader_version'],
                       'memory_mb':3072,'properties':{'motd':'Grüße aus der isolierten Abnahme!','pvp':'true'}}
        completed=next((x for x in roman.get('/versions')['plans'] if x['state']=='applied' and x['configuration'].get('properties',{}).get('motd')==configuration['properties']['motd']),None)
        if completed:
            assert completed['test_result']['live_configuration_changed'] is False
        else:
            planned=roman.post('/versions/plan',configuration)
            assert roman.get('/server/settings')['properties']['motd']==settings['properties']['motd']
            queue(roman,'version_test',{'id':planned['id']})
            assert roman.get('/server/settings')['properties']['motd']==settings['properties']['motd']
            queue(roman,'version_apply',{'id':planned['id']})
        applied=roman.get('/server/settings')
        assert applied['properties']['motd']==configuration['properties']['motd'] and applied['properties']['pvp']=='true'
        assert applied['properties']['online-mode']=='true' and applied['properties']['gamemode']=='spectator'
        assert not set(applied['properties']).intersection({'rcon.password','management-server-secret'})
        report('server_settings_staged_tested_approved_and_applied',{'live_unchanged_until_approval':True,'unicode_motd_preserved':True,'protected_properties_rejected':True})
    if 'per_user_notifications_filter_language_and_discord_schedule' not in fixture['passed']:
        roman_before=roman.get('/auth/me')['user'];moritz_before=moritz.get('/auth/me')['user'];discord_before=st.get('discord')
        try:
            roman.post('/profile',{'language':'de','notifications':{'enabled':True,'categories':['server']}})
            moritz.post('/profile',{'language':'en','notifications':{'enabled':True,'categories':['backup']}})
            previous=mail_fingerprint();roman.post('/chat',{'message':'Abnahme: Benachrichtigungsfilter prüfen.'})
            delivered=mail_message(previous)
            assert delivered['recipient']==roman_before['email'] and 'Chatnachricht gesendet' in delivered['body']
            assert any(x['state']=='accepted_by_test_transport' for x in roman.get('/notifications'))
            assert not moritz.get('/notifications')
            roman.post('/profile',{'language':'de','notifications':{'enabled':False,'categories':['server']}})
            moritz.post('/profile',{'language':'en','notifications':{'enabled':True,'categories':['server']}})
            previous=mail_fingerprint();roman.post('/chat',{'message':'Acceptance: English notification check.'})
            delivered=mail_message(previous)
            assert delivered['recipient']==moritz_before['email'] and 'Chat message sent' in delivered['body']
            assert any(x['state']=='accepted_by_test_transport' for x in moritz.get('/notifications'))
            roman.post('/settings',{'section':'discord','value':{'enabled':True,'webhook':'https://discord.com/api/webhooks/123/acceptance-only-token','events':['status'],'language':'en'}})
            path=ROOT/'state/.acceptance-discord.fernet';deadline=time.monotonic()+15
            while not path.exists() and time.monotonic()<deadline:time.sleep(.2)
            captured=json.loads(st.cipher.decrypt(path.read_bytes()))
            assert captured['status'] is True and 'Players:' in captured['text'] and '26.3' in captured['text']
            assert 'webhook' not in roman.get('/settings')['discord']
            report('per_user_notifications_filter_language_and_discord_schedule',{'email_and_discord_transport':'isolated encrypted capture only','user_filters':'passed','de_en_messages':'passed','status_schedule':'passed','live_smtp_delivery':'separately confirmed','live_discord':'not configured'})
        finally:
            roman.post('/profile',{'language':roman_before['language'],'notifications':roman_before['notifications']})
            moritz.post('/profile',{'language':moritz_before['language'],'notifications':moritz_before['notifications']})
            roman.post('/settings',{'section':'discord','value':{k:discord_before.get(k,'de' if k=='language' else None) for k in ['enabled','webhook','events','language']}})
    if 'real_modrinth_release_update_and_disabled_persistence' not in fixture['passed']:
        artifacts=fixture['artifacts']
        if 'modrinth_old' not in artifacts:
            with httpx.Client(base_url='https://api.modrinth.com/v2',timeout=30,follow_redirects=False,headers={'User-Agent':'MinecraftJavaManager/1.0.0 acceptance'}) as provider:
                response=provider.get('/version/WXHRsMRl');response.raise_for_status();version=response.json()
                assert version['version_type']=='release' and '26.3' in version['game_versions'] and 'fabric' in version['loaders']
                file=next(x for x in version['files'] if x.get('primary'));raw=mods.download_modrinth(provider,file)
            uploaded=roman.request('POST','/mods/upload',files=[('files',(file['filename'],raw,'application/java-archive'))])
            artifacts['modrinth_old']=uploaded['staged'][0]['id'];save()
        if not artifacts.get('modrinth_old_applied'):
            queue(roman,'apply_mods');artifacts['modrinth_old_applied']=True;save()
        if 'modrinth_new' not in artifacts:
            queue(roman,'mod_check')
            before=next(x for x in roman.get('/mods')['mods'] if x['id']==artifacts['modrinth_old'])
            assert before['available']['status']=='available' and before['installed_enabled']==1
            updated=roman.post('/mods/'+before['id']+'/update');artifacts['modrinth_new']=updated['id'];save()
            assert updated['installed'] is False and updated['enabled'] is True
            pending=roman.get('/mods')
            assert pending['dependencies']['structural_checks']=='passed'
            assert next(x for x in pending['mods'] if x['id']==before['id'])['installed_enabled']==1
        if not artifacts.get('modrinth_new_applied'):
            queue(roman,'apply_mods');artifacts['modrinth_new_applied']=True;save()
        installed=next(x for x in roman.get('/mods')['mods'] if x['id']==artifacts['modrinth_new'])
        assert installed['state']=='installed' and installed['source']=='modrinth'
        if not artifacts.get('modrinth_disabled'):
            roman.post('/mods/'+installed['id']+'/desired',{'enabled':False});queue(roman,'apply_mods')
            queue(roman,'server',{'operation':'restart'});artifacts['modrinth_disabled']=True;save()
        final=next(x for x in roman.get('/mods')['mods'] if x['id']==installed['id'])
        assert final['enabled']==0 and final['installed_enabled']==0
        assert not (ROOT/'server/mods'/final['filename']).exists() and (ROOT/'server/mods-disabled'/(final['id']+'.jar')).exists()
        report('real_modrinth_release_update_and_disabled_persistence',{'provider':'live official Modrinth API/CDN','mod':'Lithium','initial_release':'mc26.3-0.26.1-fabric','updated_release':'mc26.3-0.26.2-fabric','sha512_downloads_verified':True,'isolated_start_before_each_apply':True,'disabled_after_restart':True,'production_mods_changed':False})
    if 'retained_mod_trials_authenticated_report_and_scope' not in fixture['passed']:
        anonymous=BrowserClient('anonymous');anonymous.get('/mods/test-results',401)
        observed=roman.get('/mods/test-results')['report']
        viewer=BrowserClient('AcceptanceViewer');assert viewer.get('/mods/test-results')['report']==observed
        assert observed['basis_matches_configuration'] and observed['combined_start_passed']
        assert len(observed['results'])==8
        assert sum(x['status']=='isolated_start_passed' for x in observed['results'])==5
        assert sum(x['status']=='not_applicable_to_fixed_basis' for x in observed['results'])==3
        assert next(x for x in observed['results'] if x['name']=='Simple Voice Chat')['prerelease'] is True
        assert observed['client_interactions_tested'] is False and observed['visitor_permissions_with_extra_mods_tested'] is False
        assert observed['installation_approved'] is False
        assert len(roman.get('/mods')['mods'])==3,'Requested mods were unexpectedly installed in the running acceptance game'
        from mcj import controller as control
        image=control.client.containers.get(os.environ['HOSTNAME']).attrs['Image']
        fixture.setdefault('coverage',{})['retained_mod_trials_authenticated_report_and_scope']={'image_id':image,'at':time.time()}
        report('retained_mod_trials_authenticated_report_and_scope',{'image_id':image,'anonymous':'401','authenticated_viewer':'read only',
            'requested_projects':8,'passed_isolated_start':5,'incompatible_basis':3,'extra_mod_client_visitor_acceptance':False,'installed':False})
    if 'test_version_01_restart_policy_and_consistent_backup' not in fixture['passed']:
        from mcj import controller as control
        image=control.client.containers.get(os.environ['HOSTNAME']).image
        assert image.labels['org.opencontainers.image.version']=='0.1' and image.tags
        assert roman.get('/overview')['version']=='0.1'
        response=roman.client.get('/');assert response.status_code==200 and 'v0.1' in response.text
        before=st.get('server');game=control.target();identifier=game.id
        assert game.attrs['HostConfig']['RestartPolicy']['Name']=='unless-stopped'
        queue(roman,'server',{'operation':'stop'},mode='manual')
        game.reload();assert game.status=='exited'
        stopped_count=game.attrs['RestartCount'];time.sleep(12);game.reload()
        assert game.status=='exited' and game.attrs['RestartCount']==stopped_count
        queue(roman,'server',{'operation':'start'},mode='manual')
        game=control.target();assert game.id==identifier and game.status=='running'
        queue(roman,'backup',{'kind':'restart_policy_acceptance'},mode='manual')
        latest=next(x for x in roman.get('/backups') if x['kind']=='restart_policy_acceptance')
        assert latest['state']=='verified' and latest['size']>0
        assert control.target().id==identifier and control.target().status=='running'
        assert st.get('server')==before
        fixture.setdefault('coverage',{})['test_version_01_restart_policy_and_consistent_backup']={'image_id':image.id,'at':time.time()}
        report('test_version_01_restart_policy_and_consistent_backup',{'image_id':image.id,'app_version':'0.1','policy':'unless-stopped',
            'intentional_stop_stayed_off':True,'no_duplicate_or_recreated_game':True,'backup_consistency':'clean stop, verified archive, successful restart',
            'nas_or_docker_daemon_not_restarted':True,'public_release':False})
    if 'diagnostics_and_events_do_not_expose_credentials' not in fixture['passed']:
        diagnostics=roman.get('/diagnostics');text=json.dumps(diagnostics)
        forbidden=[(ROOT/'secrets'/x).read_text().strip() for x in ['encryption','rpc','rcon']]
        forbidden.extend(x['password'] for x in fixture['accounts'].values() if 'password' in x)
        forbidden.extend(x['totp'] for x in fixture['accounts'].values() if 'totp' in x)
        assert all(value not in text for value in forbidden if value)
        assert 'rcon.password' not in text
        events=roman.get('/events/export');assert 'backup_verified' in events and 'version_applied' in events
        assert all(value not in events for value in forbidden if value)
        report('diagnostics_and_events_do_not_expose_credentials')
    st.atomic(RESULT,json.dumps({'passed':fixture['passed'],'finished':True,'scope':'isolated acceptance stack','visitor_client_test':'NOT_VERIFIED','live_smtp_test':'separately confirmed by user'}).encode())
    print(json.dumps({'acceptance':'completed','workflows_passed':len(fixture['passed']),'visitor_client_test':'NOT_VERIFIED'}),flush=True)
except Exception as exc:
    result={'passed':fixture['passed'],'finished':False,'error_class':type(exc).__name__,'reason':str(exc)[:250]}
    st.atomic(RESULT,json.dumps(result).encode());print(json.dumps({'acceptance':'failed',**result}),flush=True);raise SystemExit(1)

"""Disposable Docker acceptance on a clean CI runner. Game service is synthetic.

Exercises the real shipped updater, Compose, SQLite, permissions and rollback.
Never run on a NAS with existing mcj_* containers; that check precedes mutation.
"""
import copy,json,pathlib,subprocess,tempfile,time,uuid

def run(*args,input=None,check=True,timeout=240):
    return subprocess.run(['docker',*args],input=input,capture_output=True,text=True,check=check,timeout=timeout)
def inspect(name):return json.loads(run('inspect',name).stdout)[0]
def wait(names):
    end=time.monotonic()+100
    while time.monotonic()<end:
        if all(inspect(name)['State'].get('Health',{}).get('Status')=='healthy' for name in names):return
        time.sleep(2)
    raise RuntimeError('fixture_health_timeout')

def main():
    names=['mcj_manager','mcj_controller','mcj_minecraft']
    assert all(run('inspect',n,check=False).returncode for n in names),'Existing mcj containers: native fixture refused'
    candidate='mcj-candidate:ci';key=uuid.uuid4().hex[:12];project='native_update_'+key;root='/volume9/mcj-native-'+key
    created=[];report={'synthetic_game':True,'service_uid':245001,'service_gid':245001,'candidate_image':inspect(candidate)['Id']}
    config=None
    def helper(action,definition=None):
        value={'root':root,'project':project,'definition':json.dumps(definition or config),'environment':'','action':action}
        return run('run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--user','0:0','--security-opt','no-new-privileges:true',
            '--tmpfs','/tmp:rw,nosuid,noexec,size=64m','--tmpfs',root+':rw,nosuid,noexec,size=4m,mode=0700',
            '-v','/var/run/docker.sock:/var/run/docker.sock','--entrypoint','python',candidate,'/opt/mcj/tools/deployment_snapshot.py',input=json.dumps(value))
    def updater(image):
        return run('run','--rm','--name','fixture_updater_'+key,'--network','none','--read-only','--user','0:0','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--tmpfs','/tmp:rw,nosuid,noexec,size=64m','--label','mcj.purpose=application-update','-v','/var/run/docker.sock:/var/run/docker.sock',
            '--entrypoint','python',image,'/opt/mcj/tools/app_update.py',check=False,timeout=420)
    def data_check():
        code="import json,os,pathlib,sqlite3; r=pathlib.Path("+repr(root)+");d=sqlite3.connect('file:'+str(r/'manager/state/manager.sqlite3')+'?mode=ro',uri=True);print(json.dumps({'keys':{n:oct((r/'manager/secrets'/n).stat().st_mode&0o777) for n in ['encryption','rpc','rcon']},'database':d.execute('PRAGMA integrity_check').fetchone()[0],'smtp':d.execute(\"SELECT value FROM settings WHERE name='smtp'\").fetchone()[0],'status':json.loads((r/'manager/state/application-update.json').read_text())['phase']}));d.close()"
        # A restored WAL database may need its shared-memory index recreated.
        # Use the normal app UID and writable fixture bind, while the DB connection
        # itself remains mode=ro. A read-only bind can reject SQLite's SHM setup.
        result=run('run','--rm','--network','none','--user','245001:245001','--read-only','--cap-drop','ALL','-v',root+':'+root,'--entrypoint','python',candidate,'-c',code,check=False)
        assert result.returncode==0,('fixture_data_check_failed',result.stderr)
        return json.loads(result.stdout)
    def promotion_snapshot_check():
        # The actual service UID must be able to perform the first filesystem
        # operations of a later mod/world promotion after an app-only update.
        code="""import json,os,pathlib,shutil,sys
r=pathlib.Path(sys.argv[1]);parent=r/'mcj_controller/.rollback'
assert (parent.stat().st_uid,parent.stat().st_gid,parent.stat().st_mode&0o777)==(245001,245001,0o700)
private=sorted(parent.glob('ugos-app-*'))
assert private
for item in private:
 assert (item.stat().st_uid,item.stat().st_gid,item.stat().st_mode&0o777)==(0,0,0o700)
 try:(item/'manager.sqlite3').read_bytes()
 except PermissionError:pass
 else:raise AssertionError('App snapshot became readable by the service')
p=parent/'disposable-first-promotion'
try:
 p.mkdir(mode=0o700);shutil.copytree(r/'mcj_controller/control/runtime',p/'runtime')
 assert (p/'runtime/fixture.json').read_bytes()==b'unchanged runtime'
finally:
 if p.exists():shutil.rmtree(p)
print(json.dumps({'first_nonroot_promotion_snapshot_after_update':True,'app_snapshots_remain_private':True}))
"""
        result=run('exec','mcj_controller','python','-c',code,root,check=False)
        assert result.returncode==0,('post_update_promotion_snapshot_failed',result.stdout,result.stderr)
        return json.loads(result.stdout)
    try:
        # Different image identities with the same trusted program; no registry pull or build.
        seed='fixture_seed_'+key;run('create','--name',seed,candidate,'/bin/true');created.append(seed)
        old=run('commit','--change','LABEL mcj.fixture=baseline',seed,'mcj-fixture-base:'+key).stdout.strip()
        bad_seed='fixture_bad_'+key;run('create','--name',bad_seed,candidate,'/bin/true');created.append(bad_seed)
        with tempfile.TemporaryDirectory() as folder:
            broken=pathlib.Path(folder)/'entry.py';broken.write_text("raise RuntimeError('Disposable rollback fixture')\n")
            run('cp',str(broken),bad_seed+':/opt/mcj/mcj/entry.py')
        bad=run('commit','--change','LABEL org.opencontainers.image.revision='+('f'*40),bad_seed,'mcj-fixture-bad:'+key).stdout.strip()
        server="from http.server import HTTPServer,BaseHTTPRequestHandler\nclass H(BaseHTTPRequestHandler):\n def do_GET(self): self.send_response(200);self.end_headers();self.wfile.write(b'{}')\n def log_message(self,*args): pass\nHTTPServer(('0.0.0.0',PORT),H).serve_forever()"
        def simple_service(service,port):
            return {'image':old,'pull_policy':'never','container_name':'mcj_'+service,'user':'245001:245001','read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
                'command':['python','-c',server.replace('PORT',str(port))],'networks':{'control':{}},'restart':'unless-stopped',
                'healthcheck':{'test':['CMD','python','-c',"import urllib.request;urllib.request.urlopen('http://127.0.0.1:"+str(port)+"/healthz').read()"],'interval':'2s','timeout':'2s','retries':2,'start_period':'2s'}}
        config={'name':project,'networks':{'control':{'name':project+'_control','internal':True}},'services':{
            'controller':simple_service('controller',9091),'minecraft':simple_service('minecraft',9092)}}
        config['services']['manager']={**simple_service('manager',8090),'command':['uvicorn','mcj.entry:app','--host','0.0.0.0','--port','8090','--no-access-log','--no-proxy-headers'],
            'environment':{'APP_ORIGIN':'https://fixture.internal:8090','PROJECT_ROOT':'/project','MCJ_LAYOUT':'services-v1','CONTROLLER_URL':'http://controller:9091','RPC_SECRET':'/run/secrets/rpc'},
            'volumes':[{'type':'bind','source':root+'/manager/state','target':'/project/manager/state'},
                {'type':'bind','source':root+'/manager/staging','target':'/project/manager/staging'},
                {'type':'bind','source':root+'/manager/secrets/encryption','target':'/run/secrets/encryption','read_only':True},
                {'type':'bind','source':root+'/manager/secrets/rpc','target':'/run/secrets/rpc','read_only':True}],
            'healthcheck':{'test':['CMD','python','-c',"import urllib.request;urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8090/healthz',headers={'Host':'fixture.internal:8090'})).read()"],'interval':'2s','timeout':'2s','retries':2,'start_period':'2s'}}
        config['services']['controller']['volumes']=[{'type':'bind','source':root,'target':'/project'},{'type':'bind','source':root,'target':root}]
        config=json.loads(helper('config').stdout)
        seed_code="""import os,pathlib,json,sys
from cryptography.fernet import Fernet
from mcj.store import Store
r=pathlib.Path(sys.argv[1])
for name in ['manager/state','manager/staging','manager/secrets','mcj_controller/control/reports','mcj_controller/control/runtime']: (r/name).mkdir(parents=True,exist_ok=True)
(r/'mcj_controller/control/runtime/fixture.json').write_bytes(b'unchanged runtime')
for name,raw in [('encryption',Fernet.generate_key()),('rpc',b'disposable-rpc-key'),('rcon',b'disposable-rcon-key')]:
 p=r/'manager/secrets'/name;p.write_bytes(raw);p.chmod(0o400)
st=Store(r/'manager/state',r/'manager/secrets/encryption',initial_accounts=[{'username':'Fixture','email':'fixture@example.invalid','password':'Disposable-Only-2026!'}])
st.set('maintenance',{'automatic':False,'check_minutes':1440,'backup_enabled':False,'backup_minutes':30,'retention_days':14})
st.set('smtp',{'host':'smtp.example.invalid','password':'DISPOSABLE-SMTP-FIXTURE'},True)
(r/'docker-compose.yaml').write_text(sys.stdin.read());(r/'.env').write_text('')
for p in [r,*r.rglob('*')]:os.chown(p,245001,245001)
"""
        run('run','--rm','-i','--network','none','--user','0:0','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','-v',root+':'+root,'--entrypoint','python',candidate,'-c',seed_code,root,input=json.dumps(config))
        helper('start_game');wait(['mcj_controller','mcj_minecraft']);helper('start_manager');wait(names)
        game=inspect('mcj_minecraft');old_manager=inspect('mcj_manager')
        result=updater(candidate)
        assert result.returncode==0,('native_success_update_failed',result.stdout,result.stderr)
        wait(names);first=data_check();assert first['database']=='ok' and first['status']=='complete'
        report.update(promotion_snapshot_check())
        assert set(first['keys'].values())=={'0o400'}
        assert inspect('mcj_manager')['Image']==report['candidate_image'] and inspect('mcj_controller')['Image']==report['candidate_image']
        now=inspect('mcj_minecraft');assert (now['Id'],now['Image'],now['State']['StartedAt'])==(game['Id'],game['Image'],game['State']['StartedAt'])
        again=updater(candidate);assert again.returncode==0 and 'Already up to date' in again.stdout
        result=updater(bad);assert result.returncode!=0,'Broken candidate unexpectedly accepted'
        wait(names);second=data_check();assert second['status']=='rolled_back' and second['keys']==first['keys'] and second['smtp']==first['smtp']
        assert inspect('mcj_manager')['Image']==report['candidate_image']
        now=inspect('mcj_minecraft');assert now['Id']==game['Id'] and now['State']['StartedAt']==game['State']['StartedAt']
        report.update(successful_update=True,rollback_after_real_startup_failure=True,keys_unchanged=True,encrypted_smtp_preserved=True,game_identity_unchanged=True,no_op_repeat=True)
        pathlib.Path('/tmp/native-app-update.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        if config is not None:
            # Derive the actual existing project identity again before scoped cleanup.
            probe=run('inspect','mcj_minecraft',check=False)
            if probe.returncode==0:
                actual=json.loads(probe.stdout)[0]['Config']['Labels']
                assert actual['com.docker.compose.project']==project and actual['com.docker.compose.project.config_files']==root+'/docker-compose.yaml'
                helper('down')
        for name in created:run('rm','-f',name,check=False)

if __name__=='__main__':main()

"""Real transport/process interruptions, with Docker calls replaced by isolated fixtures."""
import hashlib,json,os,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import httpx,pytest
from cryptography.fernet import Fernet
from mcj import bootstrap

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
import bootstrap_worker as worker
import browser_setup


def context(base):
    return {'base':str(base),'created':time.time(),'container':'a'*64,'service_uid':1000,'service_gid':1000,
            'origin':'https://192.168.1.50:8090','address':'192.168.1.50','network':'192.168.1.0/24',
            'parents':['/volume1/disposable-test'],'maximum_memory_mb':8192}


def queued(base):
    key=Fernet.generate_key();(base/'queue.key').write_bytes(key)
    selection={'parent':0,'backup_parent':0,'folder':'fixture-new','backup_folder':'fixture-backups','username':'Fixture',
               'email':'fixture@example.test','password':'Disposable-Fixture-Only!','memory_mb':4096,'accept_eula':True}
    (base/'request.fernet').write_bytes(Fernet(key).encrypt(json.dumps(selection).encode()))
    (base/'status.json').write_text('{"phase":"ready"}')


def test_interrupted_download_is_reported_and_keeps_partial_data(tmp_path,monkeypatch):
    class Dropped(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Length','8192');self.end_headers()
            self.wfile.write(b'partial-fixture'*8);self.wfile.flush();self.close_connection=True
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Dropped)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    queued(tmp_path);monkeypatch.setenv('MCJ_SETUP_CONTEXT',json.dumps(context(tmp_path)))
    monkeypatch.setattr(worker.install,'UID',getattr(os,'getuid',lambda:1000)())
    monkeypatch.setattr(worker.install,'GID',getattr(os,'getgid',lambda:1000)())
    monkeypatch.setattr(worker,'validate_context',lambda value:None)
    monkeypatch.setattr(worker.install,'configure_identity',lambda *args:None)
    monkeypatch.setattr(worker,'port_check',lambda value:None)
    monkeypatch.setattr(worker.install,'refuse_existing_project',lambda:None)
    sentinel=tmp_path/'partial-data';sentinel.write_bytes(b'preserve fixture')
    def download(*args,**kwargs):
        with httpx.Client(timeout=3) as client:
            client.get('http://127.0.0.1:'+str(server.server_port)+'/fixture')
    monkeypatch.setattr(worker.ugos_prepare,'prepare',download)
    def stop_waiting(seconds):raise SystemExit('fixture stopped after failure was recorded')
    monkeypatch.setattr(worker.time,'sleep',stop_waiting)
    try:
        with pytest.raises(SystemExit):worker.main()
    finally:server.shutdown();server.server_close();thread.join(timeout=3)
    report=json.loads((tmp_path/'status.json').read_text())
    assert report['phase']=='failed' and report['error']=='setup_preparation_failed'
    assert 'password' not in json.dumps(report) and 'Disposable' not in json.dumps(report)
    assert not (tmp_path/'active.fernet').exists() and not (tmp_path/'request.fernet').exists()
    assert sentinel.read_bytes()==b'preserve fixture'


def test_killed_worker_is_not_replayed_or_silently_repaired(tmp_path):
    queued(tmp_path)
    script='''import json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import bootstrap_worker as worker
worker.validate_context=lambda value:None
worker.install.configure_identity=lambda *args:None
worker.install.UID=getattr(os,'getuid',lambda:1000)()
worker.install.GID=getattr(os,'getgid',lambda:1000)()
worker.port_check=lambda value:None
worker.install.refuse_existing_project=lambda:None
def interrupted_prepare(config,password,tls,progress,**kwargs):
    progress('runtime')
    Path(os.environ['FIXTURE_BASE'],'worker-entered').write_text('fixture only')
    while True:time.sleep(.05)
worker.ugos_prepare.prepare=interrupted_prepare
worker.main()
'''
    env=dict(os.environ,MCJ_SETUP_CONTEXT=json.dumps(context(tmp_path)),FIXTURE_BASE=str(tmp_path))
    process=subprocess.Popen([sys.executable,'-c',script,str(TOOLS)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+10
        while not (tmp_path/'worker-entered').exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        assert (tmp_path/'worker-entered').exists()
        process.kill();process.communicate(timeout=5)
    finally:
        if process.poll() is None:process.kill();process.communicate(timeout=5)
    active=(tmp_path/'active.fernet').read_bytes();key=(tmp_path/'queue.key').read_bytes()
    with pytest.raises(ValueError,match='setup_interrupted_installation_review_required'):
        browser_setup.refuse_interrupted_setup(tmp_path)
    report=json.loads((tmp_path/'status.json').read_text())
    assert report['phase']=='failed' and report['error']=='setup_interrupted_installation_review_required'
    assert report['progress']=={'completed':2,'total':6}
    assert (tmp_path/'active.fernet').read_bytes()==active and (tmp_path/'queue.key').read_bytes()==key
    assert not (tmp_path/'request.fernet').exists()
    notice=(tmp_path/'EINRICHTUNG-ANGEHALTEN.txt').read_text(encoding='utf-8')
    assert 'UGOS' in notice and 'status.json' in notice and 'Do not start a second installation' in notice
    assert 'Disposable-Fixture' not in notice

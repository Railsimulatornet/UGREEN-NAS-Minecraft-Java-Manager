"""Fresh hosted-runner proof only. Does not sign in, publish or change visibility."""
import hashlib,json,os,pathlib,re,subprocess,tempfile,time
from release_metadata import version

REPO='railsimulatornet/ugreen-nas-minecraft-java-manager'
def command(*args,**kwargs):
    return subprocess.check_output(args,text=True,**kwargs).strip()

def main():
    assert os.environ.get('PUBLISH_IMAGE','false')!='true', 'Anonymous probe cannot publish images'
    revision=os.environ['EXPECTED_REVISION'];digest=os.environ['EXPECTED_DIGEST']
    assert re.fullmatch('[0-9a-f]{40}',revision)
    assert re.fullmatch('sha256:[0-9a-f]{64}',digest)
    assert command('git','rev-parse','HEAD')==revision
    assert not command('docker','image','ls','-q',REPO), 'MCJ image already present'
    manifests=json.loads(pathlib.Path('artifacts/catalog.json').read_text())['manifests']
    guards=[json.loads((pathlib.Path('artifacts')/name).read_text()) for name in manifests]
    report={'source_revision':revision,'expected_digest':digest,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'existing_mcj_image':False,'login_performed':False,'registry_credentials_present':False,'tags':[]}
    with tempfile.TemporaryDirectory(prefix='mcj-anonymous-docker-') as config:
        env={**os.environ,'DOCKER_CONFIG':config}
        assert not list(pathlib.Path(config).iterdir())
        app_version=version(pathlib.Path(__file__).resolve().parents[2])
        for tag in (app_version,'stable'):
            reference=REPO+':'+tag
            subprocess.run(['docker','pull','--platform','linux/amd64',reference],env=env,check=True)
            info=json.loads(command('docker','image','inspect',reference,env=env))[0]
            assert REPO+'@'+digest in info['RepoDigests']
            assert info['Architecture']=='amd64' and info['Os']=='linux'
            assert info['Config']['Labels']['org.opencontainers.image.revision']==revision
            assert info['Config']['Labels']['org.opencontainers.image.version']==app_version
            if not report['tags']:
                script="import json;from mcj.guard_bundle import read;print(json.dumps([{'minecraft':g['minecraft'],'java':g['java'],'version':g['version'],'sha256':g['sha256'],'visitor_verified':g['visitor_verified']} for g in read()['artifacts']]))"
                result=json.loads(command('docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--user','65534:65534','--entrypoint','python',reference,'-c',script,env=env))
                assert result==[{key:g[key] for key in ['minecraft','java','version','sha256','visitor_verified']} for g in guards]
                report['bundled_guards']=result
            report['tags'].append({'reference':reference,'image_id':info['Id'],'registry_digest':digest,'platform':'linux/amd64'})
        assert not (pathlib.Path(config)/'config.json').exists(), 'Unexpected credential configuration'
    report.update(result='passed',completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    pathlib.Path('/tmp/anonymous-installation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()

"""Connected native backup/version/restore checks under the three-folder layout."""
name='organized_three_folder_layout_preserves_accounts_and_native_maintenance'
from mcj import controller as c
from mcj.project_paths import project_path
assert c.PROJECT=='mcj_layout_acceptance_20261025'
assert os.environ['MCJ_LAYOUT']=='services-v1'
roman=enroll('Roman','totp');roman.reauthenticate()
with st.db() as db:
    users_before=db.execute('SELECT id,username,email,password,admin,enabled,factor,totp FROM users ORDER BY id').fetchall()
    secrets_before=db.execute('SELECT name,value,secret FROM settings WHERE secret=1 ORDER BY name').fetchall()
initial=roman.get('/versions')['current'];worlds_before={x['name'] for x in roman.get('/worlds')['worlds']}
assert {'world','AcceptanceImported'}<=worlds_before
assert roman.get('/overview')['status']['container_status']=='running'
c.guard_integrity();assert c.player_count()==0
prefix,service,config=c.compose_context();assert prefix[3]==c.PROJECT and service=='minecraft'
assert config['services']['minecraft']['volumes'][0]['source'].startswith(os.environ['HOST_PROJECT_ROOT']+'/')
assert not any(x.get('source')=='/var/run/docker.sock' for x in config['services']['manager']['volumes'])
plan=roman.post('/versions/plan',{'version':initial['version'],'java':initial['java'],'loader':initial['loader'],
    'loader_version':initial['loader_version'],'properties':{'motd':'Strukturprüfung – Grüße aus der Abnahme'}})
assert plan['metadata_checks']=='passed',plan.get('issues')
_,tested=queue(roman,'version_test',{'id':plan['id']})
assert tested['state']=='isolated_server_verified'
_,applied=queue(roman,'version_apply',{'id':plan['id']})
assert applied['state']=='applied'
assert c.read_properties()['motd']=='Strukturprüfung – Grüße aus der Abnahme'
assert project_path(c.ROOT,'server').is_dir() and not (c.ROOT/'server').exists()
assert project_path(c.ROOT,'staging').is_dir() and not (c.ROOT/'staging').exists()
assert list(project_path(c.ROOT,'.rollback').glob('*/journal.json'))
backup_id=applied['backup_id']
record=next(x for x in roman.get('/backups/history')['records'] if x['id']==backup_id)
assert record['archive_available'] and record['archive_state']=='available'
_,restored=queue(roman,'restore',{'id':backup_id,'confirmation':'restore '+backup_id})
assert restored['state']=='applied'
assert c.read_properties().get('motd')==initial['properties'].get('motd')
assert {x['name'] for x in roman.get('/worlds')['worlds']}==worlds_before
with st.db() as db:
    assert users_before==db.execute('SELECT id,username,email,password,admin,enabled,factor,totp FROM users ORDER BY id').fetchall()
    assert secrets_before==db.execute('SELECT name,value,secret FROM settings WHERE secret=1 ORDER BY name').fetchall()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert c.player_count()==0;c.guard_integrity();c.wait_health()
image=c.client.containers.get('mcj_layout_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'scope':'independent_organized_layout_copy; production untouched','app_image':image,
    'sqlite_and_encrypted_settings':'preserved','worlds':sorted(worlds_before),'native_version_test_and_apply':'passed',
    'actual_restore_to_original_configuration':'passed','prechange_backup':backup_id,
    'controller_compose_identity':'actual labels with explicit project','web_docker_socket':False})

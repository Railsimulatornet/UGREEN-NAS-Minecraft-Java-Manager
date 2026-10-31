"""Private native guard update and authenticated settings; client abilities pending."""
name='fine_minecraft_roles_native_guard_update_and_settings_authorization'
from mcj import controller as c
from mcj.project_paths import project_path
from mcj.role_permissions import defaults
assert c.PROJECT=='mcj_layout_acceptance_20261025'
roman=enroll('Roman','totp');roman.reauthenticate();viewer=enroll('AcceptanceViewer','totp')
viewer.get('/players/permissions',expected=403)
viewer.post('/players/permissions',{'roles':defaults()},expected=403)
roman.post('/players/permissions',{'roles':{**defaults(),'visitor':['kick']}},expected=409)
roman.post('/players/permissions',{'roles':{**defaults(),'moderator':['op']}},expected=409)
before=roman.get('/players/permissions');assert not before['supported']
current=roman.get('/versions')['current']
plan=roman.post('/versions/plan',{key:current[key] for key in ['version','java','loader','loader_version']})
assert plan['metadata_checks']=='passed',plan.get('issues')
assert plan['guard']['sha256']=='52b3dd5df344e33bbc9e2e671aceb6d9f0876821bbd925d70b1027069d99cb70'
_,tested=queue(roman,'version_test',{'id':plan['id']});assert tested['state']=='isolated_server_verified'
_,applied=queue(roman,'version_apply',{'id':plan['id']});assert applied['state']=='applied'
read=roman.get('/players/permissions');assert read['supported']
value=defaults();value['moderator']=['announce']
saved=roman.post('/players/permissions',{'roles':value});assert not saved['restart_required']
assert roman.get('/players/permissions')['roles']==value
value=defaults();roman.post('/players/permissions',{'roles':value})
assert json.loads(project_path(c.ROOT,'control/roles/permissions.json').read_text())['roles']==value
heartbeat=json.loads(project_path(c.ROOT,'control/reports/guard-status.json').read_text())
assert heartbeat['permissions_protocol']=='mcj_roles_v1' and heartbeat['online_mode']
c.guard_integrity()
guard=json.loads(project_path(c.ROOT,'control/runtime/guard.json').read_text())
assert guard['sha256']=='52b3dd5df344e33bbc9e2e671aceb6d9f0876821bbd925d70b1027069d99cb70'
assert not guard['visitor_verified']
_,restored=queue(roman,'restore',{'id':tested['backup_id'],'confirmation':'restore '+tested['backup_id']})
assert restored['state']=='applied'
guard=json.loads(project_path(c.ROOT,'control/runtime/guard.json').read_text())
assert guard['sha256']==plan['guard']['sha256']
assert roman.get('/players/permissions')['roles']==defaults()
image=c.client.containers.get('mcj_layout_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'scope':'private organized clone only','guard_sha256':guard['sha256'],'app_image':image,
    'backup_before_test':tested['backup_id'],'backup_before_apply':applied['backup_id'],
    'native_guard_start':'passed','viewer_and_visitor_grant_denied':'passed','configured_abilities_read_back':'passed',
    'old_backup_restored_with_current_guard':'passed','client_command_and_visitor_checks':'NOT_TESTED','production_changed':False,'public_approval':False})

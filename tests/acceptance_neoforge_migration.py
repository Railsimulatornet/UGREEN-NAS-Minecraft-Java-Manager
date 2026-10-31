"""Authenticated UI API -> backup -> isolated NeoForge test -> clone-only promotion."""
name='neoforge_version_plan_and_native_migration_with_seven_mods'
roman=enroll('Roman','totp');roman.reauthenticate()
viewer=enroll('AcceptanceViewer','totp')
target={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.97'}
viewer.post('/versions/plan',target,403)
catalog=json.loads((ROOT/'state/mod-trials/neoforge263-candidates-patched.json').read_text())
assert len(catalog['files'])==7
with st.db() as db:
    existing=[dict(x) for x in db.execute("SELECT * FROM mods WHERE source!='system' AND state NOT IN ('superseded','rejected')")]
for row in existing:
    if row['enabled']:roman.post('/mods/'+row['id']+'/desired',{'enabled':False})
uploads=[]
for item in catalog['files']:
    raw=(ROOT/'staging'/(item['sha256']+'.jar')).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==item['sha256']
    uploads.append(('files',(item['filename'],raw,'application/java-archive')))
staged=roman.request('POST','/mods/upload',files=uploads)
assert len(staged['staged'])==7
for item in staged['staged']:roman.post('/mods/'+item['id']+'/desired',{'enabled':True})
before=roman.get('/overview')['server'];plan=roman.post('/versions/plan',target)
assert plan['metadata_checks']=='passed',json.dumps(plan['issues'])
assert plan['configuration']['loader_components']['loader']=='NEOFORGE'
assert roman.get('/overview')['server']==before
print(json.dumps({'progress':'neoforge_metadata_and_authenticated_plan','state':'passed','plan_id':plan['id']}),flush=True)
_,tested=queue(roman,'version_test',{'id':plan['id']})
assert tested['state']=='isolated_server_verified' and not tested['live_configuration_changed']
assert roman.get('/overview')['server']==before
_,applied=queue(roman,'version_apply',{'id':plan['id']})
assert applied['state']=='applied' and applied['runtime']['loader']=='NEOFORGE'
assert applied['isolated_test']['state']=='isolated_server_verified'
overview=roman.get('/overview');assert all(overview['server'][key]==value for key,value in target.items())
active=roman.get('/mods')['mods'];wanted={x['sha256'] for x in catalog['files']}
assert {x['sha256'] for x in active if x['installed_enabled'] and x['source']!='system'}==wanted
assert roman.get('/mods')['dependencies']['structural_checks']=='passed'
from mcj import controller as c
c.guard_integrity();assert c.player_count()==0
assert json.loads((ROOT/'control/runtime/runtime.json').read_text())['loader']=='NEOFORGE'
assert not c.target().attrs['HostConfig'].get('Privileged')
assert all(x['HostIp']=='127.0.0.1' for port in c.target().attrs['HostConfig']['PortBindings'].values() for x in port)
image=c.client.containers.get('mcj_acceptance_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'scope':'acceptance_only','metadata_and_maven_ranges':'passed','viewer_denied':True,
    'full_backup_before_test':tested['backup_id'],'full_backup_before_apply':applied['backup_id'],
    'native_isolated_test':'passed','native_apply':'passed','loader_artifact_hash_verified':True,
    'seven_active_mod_hashes':sorted(wanted),'rollback_id':applied['rollback_id'],
    'client_rights_for_recorded_mod_set':'separate_retained_real_client_evidence','production_changed':False,'image_id':image})

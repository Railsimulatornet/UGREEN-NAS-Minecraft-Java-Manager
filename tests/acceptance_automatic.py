"""Real five-minute idle scheduling, backup and native apply; simulated provider only."""
name='automatic_mod_staging_idle_five_minutes_native_apply_and_disabled_persistence'
roman=enroll('Roman','totp');roman.reauthenticate()
from mcj import automatic,sources,controller as c
def resource_mod(version):
    value=io.BytesIO()
    with zipfile.ZipFile(value,'w') as z:
        z.writestr('META-INF/neoforge.mods.toml','modLoader="lowcodefml"\nloaderVersion="[1,)"\nlicense="All rights reserved"\n[[mods]]\nmodId="acceptance_auto_disabled"\nversion="'+version+'"\n[[dependencies.acceptance_auto_disabled]]\nmodId="minecraft"\ntype="required"\nversionRange="[26.3]"\n')
    return value.getvalue()
initial=roman.request('POST','/mods/upload',files=[('files',('acceptance-auto-1.0.jar',resource_mod('1.0'),'application/java-archive'))])['staged'][0]
roman.post('/mods/'+initial['id']+'/desired',{'enabled':False})
_,base_applied=queue(roman,'apply_mods')
assert base_applied['state']=='applied'
cfg=st.get('maintenance');assert not cfg['automatic']
roman.post('/settings',{'section':'maintenance','value':{**cfg,'automatic':True}})
cancelled_id=roman.post('/jobs',{'kind':'apply_mods','mode':'idle_5min','payload':{'automatic':True},'approved':True})['id']
roman.post('/settings',{'section':'maintenance','value':cfg})
assert next(x for x in roman.get('/jobs') if x['id']==cancelled_id)['state']=='cancelled'
roman.post('/settings',{'section':'maintenance','value':{**cfg,'automatic':True}})
with st.db() as db:db.execute('UPDATE mods SET available=? WHERE id=?',(json.dumps({'status':'available','version':'1.1'}),initial['id']))
original=sources.stage_update
def simulated_provider(store,root,identifier):
    assert identifier==initial['id']
    candidate=mods.stage(store,root,resource_mod('1.1'),'acceptance-auto-1.1.jar','modrinth')
    with store.db() as db:db.execute('UPDATE mods SET replaces=?,enabled=0 WHERE id=?',(identifier,candidate['id']))
    return candidate
def readiness(path,payload=None):
    if path=='/maintenance-readiness':return c.maintenance_readiness()
    if path=='/console':return {'output':c.rcon(payload['command'])}
    raise AssertionError('Unexpected automatic RPC')
def enqueue(kind,payload,actor,**values):
    return roman.post('/jobs',{'kind':kind,'payload':payload,'mode':values['mode'],'approved':values['approved']})['id']
try:
    sources.stage_update=simulated_provider
    result=automatic.stage_updates(st,ROOT,readiness,enqueue)
finally:sources.stage_update=original
assert result['state']=='queued',result
identifier=result['id'];first=next(x for x in roman.get('/jobs') if x['id']==identifier);created=first['created']
print(json.dumps({'progress':'automatic_idle_five_minutes','state':'waiting','job_id':identifier}),flush=True)
deadline=time.monotonic()+650;observed_running=False
while time.monotonic()<deadline:
    job=next(x for x in roman.get('/jobs') if x['id']==identifier)
    if job['state']!='queued':
        assert time.time()-created>=300,'Maintenance ran before five idle minutes'
        observed_running=True
    if job['state'] in ['succeeded','failed','blocked','interrupted']:
        assert job['state']=='succeeded',job['result']
        applied=json.loads(job['result']);break
    time.sleep(3)
else:raise AssertionError('Automatic native apply timed out')
assert observed_running and applied['state']=='applied' and applied['isolated_test']['state']=='isolated_server_verified'
current=roman.get('/mods')['mods'];new=next(x for x in current if x.get('replaces')==initial['id'])
assert new['state']=='installed' and not new['enabled'] and not new['installed_enabled']
assert not (ROOT/'server/mods'/new['filename']).exists() and (ROOT/'server/mods-disabled'/(new['id']+'.jar')).is_file()
roman.post('/settings',{'section':'maintenance','value':cfg})
image=c.client.containers.get('mcj_acceptance_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'scope':'acceptance_only','provider':'simulated_metadata_only_disabled_mod; real provider downloads covered separately',
    'automatic_cancel_on_disable':'passed','real_idle_wait_seconds':round(time.time()-created,1),
    'native_apply_and_isolated_start':'passed','prechange_backup':applied['backup_id'],'disabled_state_preserved':True,
    'public_runtime_automation':'blocked pending security approval','production_changed':False,'image_id':image})

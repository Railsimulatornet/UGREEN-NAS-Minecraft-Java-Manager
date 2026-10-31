"""World import and round-trip switching through the authenticated manager API."""
name='world_import_native_test_switch_and_original_world_preservation'
roman=enroll('Roman','totp');roman.reauthenticate();viewer=enroll('AcceptanceViewer','totp')
viewer.get('/worlds',403)
from mcj import controller as c,worlds
before=roman.get('/overview')['server'];original=before['world']
marker=ROOT/'server'/original/'mcj-acceptance-preserved.txt'
st.atomic(marker,'Vorhandene Welt bleibt erhalten.\n'.encode('utf-8'),0o640)
_,backup=queue(roman,'backup')
output=io.BytesIO()
import tarfile
prefix='server/'+original+'/'
with tarfile.open(c.BACKUPS/backup['path'],'r:gz') as source,zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as target:
    for item in source:
        if item.isfile() and item.name.startswith(prefix):
            relative=item.name[len(prefix):]
            if relative=='session.lock':continue
            target.writestr('AcceptedWorld/'+relative,source.extractfile(item).read())
raw=output.getvalue()
def send(client,raw,name,expected=200):
    headers={'Cookie':'__Host-mcj='+client.cookie,'X-CSRF-Token':client.csrf,'Content-Type':'application/zip'}
    response=client.client.post('/api/worlds/upload?name='+name,headers=headers,content=raw,timeout=120)
    if response.status_code!=expected:raise AssertionError('World upload: '+str(response.status_code)+' '+str(response.json().get('detail','unknown')))
    return response.json()
send(viewer,raw,'AcceptanceImported',403)
send(roman,raw,original,409)
unsafe=io.BytesIO()
with zipfile.ZipFile(unsafe,'w') as z:z.writestr('../escape',b'blocked')
send(roman,unsafe.getvalue(),'UnsafeWorld',409)
started=roman.get('/overview')['status']['started_at']
imported=send(roman,raw,'AcceptanceImported')
assert not imported['live_server_changed'] and imported['runtime_test']=='not_tested'
assert roman.get('/overview')['server']==before and roman.get('/overview')['status']['started_at']==started
assert not (ROOT/'server/AcceptanceImported').exists()
assert any(x['name']=='AcceptanceImported' for x in roman.get('/worlds')['imports'])
def switch(target):
    current=roman.get('/overview')['server']
    plan=roman.post('/versions/plan',{'version':current['version'],'java':current['java'],'loader':current['loader'],
         'loader_version':current['loader_version'],'properties':{'level-name':target}})
    assert plan['metadata_checks']=='passed'
    _,tested=queue(roman,'version_test',{'id':plan['id']})
    assert tested['state']=='isolated_server_verified' and roman.get('/overview')['server']==current
    _,applied=queue(roman,'version_apply',{'id':plan['id']})
    assert applied['state']=='applied' and roman.get('/overview')['server']['world']==target
    return tested,applied
tested,applied=switch('AcceptanceImported')
assert worlds.validate_level(ROOT/'server/AcceptanceImported/level.dat')>0
assert (ROOT/'server/AcceptanceImported'/marker.name).read_bytes()==marker.read_bytes()
assert marker.read_text()=='Vorhandene Welt bleibt erhalten.\n'
back_test,back_apply=switch(original)
assert marker.read_text()=='Vorhandene Welt bleibt erhalten.\n'
assert (ROOT/'server/AcceptanceImported/level.dat').is_file()
assert roman.get('/worlds')['current']==original
image=c.client.containers.get('mcj_acceptance_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'scope':'acceptance_only','viewer_denied':True,'duplicate_name_denied':True,'zip_traversal_denied':True,
    'upload_does_not_restart_or_change_live_world':True,'nbt_validated':True,
    'switch_and_switch_back':'passed','consistent_backups_before_test_and_apply':True,
    'original_and_imported_worlds_preserved':True,'backup_before_apply':applied['backup_id'],
    'backup_before_switch_back':back_apply['backup_id'],'production_changed':False,'image_id':image})

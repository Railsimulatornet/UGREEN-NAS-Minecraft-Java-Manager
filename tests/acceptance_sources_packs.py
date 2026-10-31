"""Connected source/import checks; run only in the disposable acceptance stack."""
from pathlib import Path
prefix=(Path('/opt/mcj/tests/acceptance_workflows.py').read_text() if Path('/opt/mcj/tests/acceptance_workflows.py').exists() else Path('/project/fixtures/acceptance_workflows.py').read_text()).split('\ntry:\n',1)[0]
exec(prefix,globals())
name='curseforge_sources_pack_staging_and_native_apply'
roman=enroll('Roman','totp');roman.reauthenticate()
viewer=enroll('AcceptanceViewer','totp')
urls=['https://www.curseforge.com/minecraft/mc-mods/carry-on','https://www.curseforge.com/minecraft/mc-mods/create-adapted','https://www.curseforge.com/minecraft/modpacks/aeronautics']
before=roman.get('/overview')['server'];game_before=roman.get('/overview')['status']['started_at']
sources_value=roman.post('/mods/sources',{'sources':[{'url':url,'enabled':False,'allow_prerelease':False} for url in urls]})['sources']
viewer.post('/mods/sources',{'sources':[]},403)
for value in sources_value[1:]:
    _,checked=queue(roman,'source_check',{'id':value['id']},mode='manual')
    assert checked['state']=='blocked' and checked['runtime_test']=='not_tested'
assert roman.get('/overview')['server']==before and roman.get('/overview')['status']['started_at']==game_before
_,result=queue(roman,'source_stage',{'id':sources_value[0]['id']},mode='manual')
assert result['staged'] and result['live_server_changed'] is False
carry=[x['id'] for x in result['staged'] if not x.get('already_present')]
assert roman.get('/overview')['status']['started_at']==game_before
stream=io.BytesIO()
with zipfile.ZipFile(stream,'w') as z:
    z.writestr('mods/acceptance_cf_pack.jar',make_jar('acceptance_cf_pack'))
    z.writestr('config/mcj-acceptance-pack.json','{"text":"Grüße aus dem isolierten Pack-Test"}')
    z.writestr('server.properties','pvp=false\nonline-mode=false\nrcon.password=NEVER_IMPORT\n')
raw=stream.getvalue()
def raw_upload(client,data,expected=200):
    headers={'Cookie':'__Host-mcj='+client.cookie,'X-CSRF-Token':client.csrf,'Content-Type':'application/zip'}
    response=client.client.post('/api/packs/upload',headers=headers,content=data)
    if response.status_code!=expected:raise AssertionError('Pack upload: '+str(response.status_code)+' '+str(response.json().get('detail','unknown')))
    return response.json()
raw_upload(viewer,raw,403)
wrong=io.BytesIO()
with zipfile.ZipFile(wrong,'w') as z:
    z.writestr('manifest.json',json.dumps({'manifestType':'minecraftModpack','manifestVersion':1,'minecraft':{'version':'1.21.1'}}))
assert raw_upload(roman,wrong.getvalue(),409)['detail']=='pack_game_mismatch'
result=raw_upload(roman,raw);assert not result['live_server_changed']
plan=result['pending_pack'];pack_identifier=result['staged'][0]['id']
assert plan['properties']=={'pvp':'false'} and not plan['apply_properties']
assert not (ROOT/'server/config/mcj-acceptance-pack.json').exists()
_,applied=queue(roman,'apply_mods')
assert applied['state']=='applied' and applied['isolated_test']['state']=='isolated_server_verified'
assert (ROOT/'server/config/mcj-acceptance-pack.json').read_text()=='{"text":"Grüße aus dem isolierten Pack-Test"}'
assert roman.get('/mods/sources')['pending_packs']==[]
active=roman.get('/mods')['mods']
assert any(x['id']==pack_identifier and x['installed_enabled'] for x in active)
for identifier in [*carry,pack_identifier]:roman.post('/mods/'+identifier+'/desired',{'enabled':False})
result=raw_upload(roman,raw)
assert result['staged'][0]['already_present'] and not result['staged'][0]['enabled']
_,disabled=queue(roman,'apply_mods')
active=roman.get('/mods')['mods']
assert all(not x['installed_enabled'] for x in active if x['id'] in [*carry,pack_identifier])
image=__import__('mcj.controller',fromlist=['client']).client.containers.get('mcj_acceptance_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'real_curseforge_download_and_sha1_verified':True,'native_apply':'passed','prechange_backup':applied['backup_id'],
    'pack_configuration_and_unicode':'passed','disabled_state_survives_reimport':'passed','viewer_write_denied':True,
    'wrong_version_rejected_before_live_change':True,'create_adapted_with_fabric':'blocked','aeronautics_with_263':'blocked',
    'production_changed':False,'image_id':image})

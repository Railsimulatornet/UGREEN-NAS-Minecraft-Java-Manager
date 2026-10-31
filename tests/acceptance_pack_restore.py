"""Restore mod provenance and pack metadata together with the actual game data."""
name='pack_and_curseforge_provenance_survive_backup_restore'
roman=enroll('Roman','totp');roman.reauthenticate()
before=st.get('pack_installations');assert before
with st.db() as db:
    rows=[dict(x) for x in db.execute("SELECT * FROM mods WHERE source='curseforge'")]
assert rows;record=rows[0];origin=record['origin'];assert json.loads(origin)['provider']=='curseforge'
configuration=ROOT/'server/config/mcj-acceptance-pack.json';raw=configuration.read_bytes()
_,backup=queue(roman,'backup',{'kind':'pack_metadata_acceptance'})
row=next(x for x in roman.get('/backups') if x['path']==backup['path']);assert row['state']=='verified'
from mcj import controller as c
import tarfile
with tarfile.open(c.BACKUPS/backup['path'],'r:gz') as tar:
    manifest=json.load(tar.extractfile('mod-manifest.json'))
    packed=json.load(tar.extractfile('pack-state.json'))
assert packed['installations']==before
assert next(x for x in manifest if x['sha256']==record['id'])['origin']==json.loads(origin)
st.set('pack_installations',{})
with st.db() as db:db.execute('UPDATE mods SET origin=? WHERE id=?',('{}',record['id']))
st.atomic(configuration,b'{"temporary":"isolated acceptance mutation"}')
try:
    _,restored=queue(roman,'restore',{'id':row['id'],'confirmation':'restore '+row['id']})
    assert restored['state']=='applied' and restored['isolated_test']['state']=='isolated_server_verified'
    assert st.get('pack_installations')==before and configuration.read_bytes()==raw
    with st.db() as db:actual=dict(db.execute('SELECT * FROM mods WHERE id=?',(record['id'],)).fetchone())
    assert actual['source']=='curseforge' and json.loads(actual['origin'])==json.loads(origin)
    assert actual['installed_enabled']==record['installed_enabled']
except BaseException:
    st.set('pack_installations',before);st.atomic(configuration,raw)
    with st.db() as db:db.execute('UPDATE mods SET origin=? WHERE id=?',(origin,record['id']))
    raise
image=c.client.containers.get('mcj_acceptance_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'backup_id':row['id'],'native_restore':'passed','pack_metadata':'restored_from_archive',
    'curseforge_provenance':'preserved','disabled_state':'preserved','unicode_configuration':'preserved',
    'production_changed':False,'image_id':image})

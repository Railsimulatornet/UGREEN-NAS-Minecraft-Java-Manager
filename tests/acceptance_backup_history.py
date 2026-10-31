"""Connected archive history, retention reconciliation and stale-action rejection."""
name='backup_history_retention_pagination_and_unavailable_restore_rejection'
roman=enroll('Roman','totp');roman.reauthenticate()
from mcj import controller as c
memory_events=Path('/sys/fs/cgroup/memory.events').read_text()
records=roman.get('/backups/history?limit=2');assert records['records'] and records['next_cursor']
seen=[];cursor=''
while True:
    result=roman.get('/backups/history?limit=2'+('&cursor='+cursor if cursor else ''))
    seen.extend(x['id'] for x in result['records']);cursor=result['next_cursor']
    if not cursor:break
assert len(seen)==len(set(seen))
with st.db() as db:
    assert len(seen)==db.execute('SELECT COUNT(*) FROM backups').fetchone()[0]
latest=next(x for x in roman.get('/backups/history?state=verified')['records'] if x['archive_available'])
checked,metadata,_=c.checked_archive(latest['path'])
assert checked.is_file() and metadata['sha256']==latest['sha256']
record=next(x for x in roman.get('/backups/history')['records'] if x['id']==latest['id'])
assert record['archive_available'] and record['archive_state']=='available'
headers={'Cookie':'__Host-mcj='+roman.cookie,'X-CSRF-Token':roman.csrf}
checksum=hashlib.sha256();downloaded=0
with roman.client.stream('GET','/api/backups/'+latest['id']+'/download',headers=headers) as response:
    assert response.status_code==200
    for chunk in response.iter_bytes(1024*1024):checksum.update(chunk);downloaded+=len(chunk)
assert downloaded==latest['size'] and checksum.hexdigest()==latest['sha256']

# Retention itself is exercised only on disposable archive files, never real backups.
original=c.BACKUPS;temporary=original/('acceptance-retention-'+secrets.token_hex(6));temporary.mkdir()
try:
    for index in range(4):
        stem='20260901T00000'+str(index)+'Z-12345678';raw=b'retention fixture'
        (temporary/(stem+'.tar.gz')).write_bytes(raw)
        value={'id':stem,'path':stem+'.tar.gz','state':'verified','created':time.time()-30*86400+index,
            'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        st.atomic(temporary/(stem+'.json'),json.dumps(value).encode())
    c.BACKUPS=temporary;expired=c.prune_backups();assert len(expired)==2
    assert len(list(temporary.glob('*.tar.gz')))==2 and len(list(temporary.glob('*.json')))==4
    assert c.prune_backups()==[]
finally:c.BACKUPS=original

identifier=secrets.token_hex(16);stem='20260901T000000Z-'+secrets.token_hex(4);path=stem+'.tar.gz'
st.atomic(original/(stem+'.json'),json.dumps({'path':path,'state':'verified','archive_state':'expired'}).encode())
with st.db() as db:db.execute('INSERT INTO backups(id,created,kind,state,path,size,sha256) VALUES(?,?,?,?,?,?,?)',
    (identifier,time.time(),'acceptance_history_test','verified',path,0,'0'*64))
record=roman.get('/backups/history?kind=acceptance_history_test')['records'][0]
assert record['id']==identifier and record['state']=='verified' and record['archive_state']=='expired' and not record['archive_available']
roman.get('/backups/'+identifier+'/download',expected=404)
for kind in ['restore','restore_test']:
    roman.post('/jobs',{'kind':kind,'payload':{'id':identifier,'confirmation':'restore '+identifier},'approved':True},expected=404)
roman.get('/backups/history?cursor=invalid',expected=400)
image=c.client.containers.get('mcj_acceptance_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'scope':'acceptance_only','archive_history_without_duplicate_rows':len(seen),
    'new_actual_consistent_backup':latest['id'],'controller_full_sha256_check':'passed',
    'retention_disposable_fixture_only':'four_attempts_two_archives_retained_no_repeat_pruning',
    'expired_attempt_remains_visible':'passed','download_restore_and_restore_test_rejected':'passed',
    'download_stream_sha256':'passed','no_new_oom_kill':memory_events==Path('/sys/fs/cgroup/memory.events').read_text()})

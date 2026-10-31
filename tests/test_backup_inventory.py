import hashlib,json,secrets,time
import pytest
from cryptography.fernet import Fernet
from mcj import backup_inventory as inventory
from mcj.store import Store


def archive(tmp_path):
    name='20261024T220000Z-12345678.tar.gz';raw=b'fixture archive'
    row={'id':secrets.token_hex(16),'created':1,'kind':'manual','state':'verified','path':name,
         'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'restore_status':'not_tested','restore_tested':None}
    (tmp_path/name).write_bytes(raw)
    metadata=tmp_path/(name[:-7]+'.json');metadata.write_text(json.dumps(row))
    return row,metadata


def test_retained_verified_history_does_not_imply_archive_available(tmp_path):
    row,metadata=archive(tmp_path)
    assert inventory.archive_info(tmp_path,row)['archive_available']
    (tmp_path/row['path']).unlink()
    assert inventory.archive_info(tmp_path,row)['archive_state']=='missing'
    metadata.write_text(json.dumps({**row,'archive_state':'expired'}))
    assert inventory.archive_info(tmp_path,row)['archive_state']=='expired'
    with pytest.raises(ValueError,match='backup_unavailable'):inventory.require_available(tmp_path,row)
    assert row['state']=='verified'  # Original successful attempt remains historical evidence.


@pytest.mark.parametrize('change',['size','hash','path','metadata_missing','expired_but_present','failed_attempt'])
def test_inconsistent_or_unverified_archives_are_unavailable(tmp_path,change):
    row,metadata=archive(tmp_path)
    if change=='size':(tmp_path/row['path']).write_bytes(b'changed')
    if change=='hash':metadata.write_text(json.dumps({**row,'sha256':'0'*64}))
    if change=='path':row['path']='../outside.tar.gz'
    if change=='metadata_missing':metadata.unlink()
    if change=='expired_but_present':metadata.write_text(json.dumps({**row,'archive_state':'expired'}))
    if change=='failed_attempt':row['state']='failed'
    assert not inventory.archive_info(tmp_path,row)['archive_available']


def test_newer_failed_restore_is_not_hidden_by_older_success(tmp_path):
    row,metadata=archive(tmp_path)
    metadata.write_text(json.dumps({**row,'restore_status':'isolated_server_verified','restore_tested':10}))
    result=inventory.archive_info(tmp_path,row);assert result['restore_tested']==10
    row.update(restore_tested=20,restore_status='failed')
    assert inventory.archive_info(tmp_path,row)['restore_status']=='failed'


def test_all_attempts_paginate_without_duplicates_at_equal_timestamps(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());st=Store(tmp_path/'state',key)
    rows=[(f'{n:032x}',100+n//100,'failed' if n%3==0 else 'verified') for n in range(2111)]
    with st.db() as db:db.executemany('INSERT INTO backups(id,created,kind,state) VALUES(?,?,\'manual\',?)',rows)
    seen=[];cursor=''
    while True:
        value=inventory.page(st,tmp_path,limit=73,cursor=cursor)
        seen.extend(x['id'] for x in value['records']);cursor=value['next_cursor']
        if not cursor:break
        if len(seen)==73:
            with st.db() as db:db.execute('INSERT INTO backups(id,created,kind,state) VALUES(?,?,?,?)',('f'*32,999,'manual','running'))
    assert len(seen)==2111==len(set(seen))
    assert seen==[x[0] for x in sorted(rows,key=lambda x:(x[1],x[0]),reverse=True)]
    result=inventory.page(st,tmp_path,state='failed',after=110,before=110,limit=100)
    assert result['records'] and all(x['state']=='failed' and x['created']==110 for x in result['records'])
    cursor=inventory.page(st,tmp_path,limit=1)['next_cursor']
    with pytest.raises(ValueError,match='invalid_backup_cursor'):inventory.page(st,tmp_path,cursor=cursor,state='failed')


@pytest.mark.parametrize('kwargs',[{'limit':0},{'limit':201},{'state':'anything'},{'kind':"x' OR 1=1"},
                                 {'after':float('nan')},{'after':5,'before':1},{'cursor':'not-a-cursor'},{'cursor':'W10'}])
def test_invalid_filters_and_cursors_fail_closed(tmp_path,kwargs):
    with pytest.raises(ValueError,match='invalid_backup_'):inventory.page(None,tmp_path,**kwargs)


@pytest.mark.parametrize('unavailable_newest',[False,True])
def test_retention_keeps_two_real_archives_and_every_attempt_record(tmp_path,unavailable_newest):
    for index in range(4):
        name='20260901T00000'+str(index)+'Z-12345678.tar.gz';raw=b'archive'
        value={'path':name,'created':index,'state':'verified','sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}
        (tmp_path/name).write_bytes(raw);(tmp_path/(name[:-7]+'.json')).write_text(json.dumps(value))
    if unavailable_newest:
        (tmp_path/'20260901T000003Z-12345678.tar.gz').unlink()
    expired=inventory.prune(tmp_path,14,now=40*86400)
    assert len(expired)==(1 if unavailable_newest else 2)
    assert len(list(tmp_path.glob('*.tar.gz')))==2
    assert len(list(tmp_path.glob('*.json')))==4
    assert inventory.prune(tmp_path,14,now=40*86400)==[]

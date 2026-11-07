"""Backup selection must use the same recovery protection as deletion."""
import hashlib
import json
import ast
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import pytest
from mcj import backup_inventory,storage_admin
from test_security import environment,enroll


def archives(st,root):
    root.mkdir()
    for number in range(1,4):
        name=f'20261025T10000{number}Z-{number:08x}.tar.gz';raw=f'backup {number}'.encode()
        value={'id':str(number)*32,'created':time.time()-10+number,'kind':'manual','state':'verified',
               'path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        (root/name).write_bytes(raw);(root/(name[:-7]+'.json')).write_text(json.dumps(value))
        with st.db()as db:
            db.execute('INSERT INTO backups(id,created,kind,state,path,size,sha256) VALUES(?,?,?,?,?,?,?)',
                       tuple(value[k]for k in ['id','created','kind','state','path','size','sha256']))


def test_history_does_not_advertise_a_rollback_backup_as_deletable(environment,tmp_path,monkeypatch):
    app,client,_,_=environment;enroll(environment);st=app.state.store
    root=tmp_path/'backups';archives(st,root);monkeypatch.setenv('BACKUP_ROOT',str(root))
    rollback=tmp_path/'rollback';journal=rollback/'previous/journal.json';journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({'backup_id':'1'*32,'state':'applied'}))
    # This is the original discrepancy: deletion rejects an otherwise valid archive.
    with pytest.raises(ValueError,match='delete_item_protected'):
        storage_admin.delete(st,root,'backup',['1'*32],1,rollback_root=rollback)
    calls=[]
    def rpc(path,payload=None):
        calls.append(path)
        assert path=='/backup/protection'and payload is None
        return {'protected_ids':['1'*32,'3'*32]}
    app.state.rpc=rpc
    response=client.get('/api/backups/history');assert response.status_code==200
    records=response.json()['records'];selected=[r['id']for r in records if r['archive_available']and not r['protected']]
    assert selected==['2'*32]
    assert calls==['/backup/protection']
    preview=storage_admin.delete(st,root,'backup',selected,1,rollback_root=rollback)
    assert preview['count']==1
    assert len(list(root.glob('*.tar.gz')))==3  # A preview never deletes a real archive.
    result=storage_admin.delete(st,root,'backup',selected,1,rollback_root=rollback,confirmation=preview['confirmation'])
    assert result['deleted']and len(list(root.glob('*.tar.gz')))==2
    assert (root/'20261025T100001Z-00000001.tar.gz').is_file()
    assert (root/'20261025T100003Z-00000003.tar.gz').is_file()


def test_history_fails_closed_when_controller_protection_cannot_be_read(environment,tmp_path,monkeypatch):
    app,client,_,_=environment;enroll(environment)
    root=tmp_path/'backups';archives(app.state.store,root);monkeypatch.setenv('BACKUP_ROOT',str(root))
    def unavailable(*args):raise RuntimeError('private controller diagnostics')
    app.state.rpc=unavailable
    response=client.get('/api/backups/history')
    assert response.status_code==503
    assert response.json()=={'detail':'backup_protection_unavailable'}


def test_shared_protection_keeps_rollback_archives_for_delete_and_retention(environment,tmp_path):
    app,_,_,_=environment;st=app.state.store;root=tmp_path/'backups';archives(st,root)
    rollback=tmp_path/'rollback';journal=rollback/'previous/journal.json';journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({'backup_id':'1'*32,'state':'applied'}))
    with st.db()as db:protected=storage_admin.backup_protection(db,root,rollback_root=rollback)
    assert protected=={'1'*32,'3'*32}
    with st.db()as db:paths={r['path']for r in db.execute('SELECT id,path FROM backups')if r['id']in protected}
    assert backup_inventory.prune(root,4,now=10*86400,protected=paths)==[]
    assert len(list(root.glob('*.tar.gz')))==3


def test_invalid_rollback_reference_blocks_protection_discovery(environment,tmp_path):
    app,_,_,_=environment;st=app.state.store;root=tmp_path/'backups';archives(st,root)
    rollback=tmp_path/'rollback';journal=rollback/'previous/journal.json';journal.parent.mkdir(parents=True)
    journal.write_text('{invalid json')
    with st.db()as db,pytest.raises(ValueError):
        storage_admin.backup_protection(db,root,rollback_root=rollback)


def test_controller_reports_the_complete_protection_set(environment,tmp_path):
    app,_,_,_=environment;st=app.state.store;root=tmp_path/'backups';archives(st,root)
    rollback=tmp_path/'project/.rollback/previous';rollback.mkdir(parents=True)
    (rollback/'journal.json').write_text(json.dumps({'backup_id':'1'*32,'state':'applied'}))
    source=(Path(__file__).parents[1]/'mcj/controller.py').read_text(encoding='utf-8')
    function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='backup_protection_status')
    function.decorator_list=[]
    scope={'__name__':__name__,'__package__':'mcj','sys':sys,'ROOT':tmp_path/'project','BACKUPS':root,
           'maintenance':SimpleNamespace(store=lambda _:st),'project_path':lambda p,relative:p/relative}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<controller backup protection>','exec'),scope)
    assert scope['backup_protection_status']()=={'protected_ids':['1'*32,'3'*32]}

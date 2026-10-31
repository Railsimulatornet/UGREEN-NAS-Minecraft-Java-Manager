import ast
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace
import pytest
from mcj import storage_preflight as space
from test_security import environment,enroll,post


def tree(tmp_path):
    root=tmp_path/'project';(root/'server/world').mkdir(parents=True)
    (root/'server/world/region.dat').write_bytes(b'x'*8193)
    (root/'server/server.properties').write_text('online-mode=true')
    (root/'backups').mkdir();return root,root/'backups'


def disk(monkeypatch,free):
    monkeypatch.setattr(space.shutil,'disk_usage',lambda _:SimpleNamespace(free=free,total=1000*space.GIB,used=0))


def test_backup_and_temporary_requirements_are_aggregated_on_the_same_volume(tmp_path,monkeypatch):
    root,backups=tree(tmp_path);disk(monkeypatch,100*space.GIB)
    value=space.forecast(root,backups,'apply_mods')
    assert value['sufficient'] and len(value['volumes'])==1
    volume=value['volumes'][0]
    assert volume['roles']==['backup','temporary'] and volume['required_bytes']>space.PREPARATION
    disk(monkeypatch,volume['required_bytes']+space.RESERVE-1)
    with pytest.raises(ValueError,match='insufficient_operation_space'):space.require(root,backups,'apply_mods')
    assert '/project' not in json.dumps(value) and 'world' not in json.dumps(value)


def test_separate_volumes_each_keep_their_own_reserve(tmp_path,monkeypatch):
    root,backups=tree(tmp_path);disk(monkeypatch,100*space.GIB)
    class Parent:
        def __init__(self,value):self.value=value
        def stat(self):return SimpleNamespace(st_dev=self.value)
    monkeypatch.setattr(space,'existing_parent',lambda p:Parent(1 if Path(p)==backups else 2))
    value=space.forecast(root,backups,'server_settings')
    assert len(value['volumes'])==2 and all(x['reserve_bytes']==20*space.GIB for x in value['volumes'])
    assert value['volumes'][0]['roles']==['backup'] and value['volumes'][1]['roles']==['temporary']


def make_archive(path,name='server/world/region.dat',size=5*1024*1024,link=False):
    with tarfile.open(path,'w:gz') as tar:
        item=tarfile.TarInfo(name);item.size=size
        if link:item.type=tarfile.SYMTYPE;item.linkname='/etc/passwd';item.size=0
        tar.addfile(item,None if link else io.BytesIO(b'\0'*size))


def test_restore_measures_expanded_bytes_instead_of_compressed_file_size(tmp_path,monkeypatch):
    root,backups=tree(tmp_path);disk(monkeypatch,100*space.GIB);archive=backups/'test.tar.gz';make_archive(archive)
    measured=space.archive_size(archive)
    assert measured['bytes']==5*1024*1024 and archive.stat().st_size<10000
    value=space.forecast(root,backups,'restore_test',archive)
    assert value['volumes'][0]['required_bytes']>=5*1024*1024+space.PREPARATION
    assert value['volumes'][0]['roles']==['temporary']


@pytest.mark.parametrize('name,link',[('../escape',False),('/absolute',False),('server/link',True),('private/secret',False)])
def test_unsafe_archive_never_generates_an_execution_forecast(tmp_path,monkeypatch,name,link):
    root,backups=tree(tmp_path);archive=backups/'test.tar.gz';make_archive(archive,name,1,link)
    with pytest.raises(ValueError,match='storage_archive_unsafe'):space.forecast(root,backups,'restore_test',archive)


def test_low_space_stops_actual_backup_function_before_shutdown_or_gate(tmp_path,monkeypatch):
    root,backups=tree(tmp_path);disk(monkeypatch,space.RESERVE)
    # Execute the actual production entry point with disposable paths and no Docker access.
    source=Path(__file__).parents[1]/'mcj/controller.py'
    function=next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='archive_backup')
    called=[];scope={'ROOT':root,'BACKUPS':backups,'storage_preflight':space,'graceful_stop':lambda *_:called.append('stop'),'gate':lambda *_:called.append('gate')}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
    with pytest.raises(ValueError,match='insufficient_operation_space'):scope['archive_backup']('manual')
    assert called==[] and list(backups.iterdir())==[]


def test_hardlinked_server_files_are_rejected(tmp_path):
    import os
    root,_=tree(tmp_path)
    os.link(root/'server/server.properties',root/'server/second.properties')
    with pytest.raises(ValueError,match='storage_inventory_unsafe'):space.tree_size(root/'server')


def test_preflight_api_is_admin_only_csrf_protected_and_uses_fixed_controller_roles(environment):
    app,client,_,_=environment
    assert post(client,'/api/storage/preflight',{'kind':'backup'}).status_code in {401,403}
    login=enroll(environment);seen=[]
    app.state.rpc=lambda path,data:seen.append((path,data)) or {'sufficient':True,'volumes':[]}
    assert post(client,'/api/storage/preflight',{'kind':'backup'}).status_code==403
    assert post(client,'/api/storage/preflight',{'kind':'arbitrary'},login['csrf']).status_code==409
    assert post(client,'/api/storage/preflight',{'kind':'backup'},login['csrf']).json()['sufficient']
    assert seen==[('/storage/preflight',{'kind':'backup'})]
    with app.state.store.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,'/api/storage/preflight',{'kind':'backup'},login['csrf']).status_code==403


def test_preflight_failure_has_a_clear_safe_error_and_no_job(environment):
    app,client,_,_=environment;login=enroll(environment)
    def unavailable(*_):raise RuntimeError('/private/path must never appear')
    app.state.rpc=unavailable
    result=post(client,'/api/storage/preflight',{'kind':'backup'},login['csrf'])
    assert result.status_code==409 and result.json()['detail']=='storage_preflight_unavailable'
    with app.state.store.db() as db:assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0

"""Historical recovery references must not keep archives forever."""
import hashlib,json
import pytest
from mcj import backup_inventory,storage_admin
from test_security import environment


def inventory(st,root,rollback):
    root.mkdir();rollback.mkdir()
    st.set('maintenance',{**st.get('maintenance'),'retention_days':4})
    # Four expired historical archives plus two current, verified backups.
    for n,created in enumerate([1,2,3,4,9*86400,9*86400+1],1):
        name=f'20261025T10000{n}Z-{n:08x}.tar.gz';raw=f'fixture {n}'.encode()
        data={'id':str(n)*32,'path':name,'created':created,'kind':'manual','state':'verified',
              'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}
        (root/name).write_bytes(raw);(root/(name[:-7]+'.json')).write_text(json.dumps(data))
        with st.db()as db:
            db.execute('INSERT INTO backups(id,created,kind,state,path,size,sha256,restored) VALUES(?,?,?,?,?,?,?,?)',
                       tuple(data[k]for k in ['id','created','kind','state','path','size','sha256'])+(100 if n==2 else None,))
    with st.db()as db:
        db.execute('INSERT INTO version_plans(id,created,updated,state,configuration,report,based_on,backup_id) VALUES(?,?,?,?,?,?,?,?)',
                   ('a'*32,1,2,'tested','{}','{}','{}','1'*32))
    for n,state in [(3,'applied'),(4,'prepared')]:
        folder=rollback/str(n);folder.mkdir()
        (folder/'journal.json').write_text(json.dumps({'backup_id':str(n)*32,'state':state,'at':n}))
        (folder/'server').mkdir();(folder/'server/keep').write_text('private rollback copy')


@pytest.mark.parametrize('active_kind',[None,'restore','restore_test','version_test','version_apply'])
def test_expired_history_is_pruned_but_active_work_and_two_current_archives_survive(environment,tmp_path,active_kind):
    app,_,_,_=environment;st=app.state.store;root=tmp_path/'backups';rollback=tmp_path/'rollback'
    inventory(st,root,rollback)
    if active_kind:
        app.state.add_job(active_kind,{'id':'a'*32 if active_kind.startswith('version')else '1'*32},1)
    with st.db()as db:
        protected=storage_admin.backup_protection(db,root,rollback_root=rollback,now=10*86400)
        paths={r['path']for r in db.execute('SELECT id,path FROM backups')if r['id']in protected}
    assert protected==({'6'*32,'1'*32}if active_kind else {'6'*32})
    expired=backup_inventory.prune(root,4,now=10*86400,protected=paths)
    assert len(expired)==(3 if active_kind else 4)
    assert len(list(root.glob('*.tar.gz')))==(3 if active_kind else 2)
    assert len(list(root.glob('*.json')))==6
    assert all((rollback/str(n)/'server/keep').read_text()=='private rollback copy'for n in [3,4])
    with st.db()as db:
        assert db.execute('SELECT COUNT(*) FROM backups').fetchone()[0]==6
        assert db.execute('SELECT state FROM version_plans').fetchone()[0]=='tested'
    assert backup_inventory.prune(root,4,now=10*86400,protected=paths)==[]


def test_recent_recovery_references_remain_protected(environment,tmp_path):
    app,_,_,_=environment;st=app.state.store;root=tmp_path/'backups';rollback=tmp_path/'rollback'
    inventory(st,root,rollback)
    with st.db()as db:
        protected=storage_admin.backup_protection(db,root,rollback_root=rollback,now=86400)
    assert protected=={'1'*32,'2'*32,'3'*32,'4'*32,'6'*32}

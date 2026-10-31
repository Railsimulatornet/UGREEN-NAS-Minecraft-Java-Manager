import json
import os
from pathlib import Path
import pytest
from mcj import runtime_storage
from test_security import environment


def fixture(root, st, snapshots=1):
    st.set('server',{'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.99'})
    relative=Path('libraries/net/neoforged/neoforge/26.3.0.97')
    live=root/'server'/relative;live.mkdir(parents=True)
    (live/'loader.jar').write_bytes(b'verified old loader')
    saved=[]
    for n in range(snapshots):
        snapshot=root/'.rollback'/('saved-'+str(n));(snapshot/'runtime').mkdir(parents=True)
        (snapshot/'runtime/runtime.json').write_text(json.dumps({'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.97'}))
        copy=snapshot/'server'/relative;copy.mkdir(parents=True)
        (copy/'loader.jar').write_bytes((live/'loader.jar').read_bytes());saved.append(copy)
    return live,saved


def test_delete_redundant_cache_preserves_every_full_rollback(environment,tmp_path):
    st=environment[0].state.store;live,saved=fixture(tmp_path,st,2)
    item=runtime_storage.inventory(tmp_path,st.get('server'))[0]
    assert item['deletable'] and item['status']=='unused' and item['independent_rollback_copies']==2
    preview=runtime_storage.delete(st,tmp_path,item['id'],1)
    assert live.is_dir()
    runtime_storage.delete(st,tmp_path,item['id'],1,preview['confirmation'])
    assert not live.exists()
    assert all((p/'loader.jar').read_bytes()==b'verified old loader' for p in saved)
    assert len(list((tmp_path/'.rollback').glob('*/runtime/runtime.json')))==2


@pytest.mark.parametrize('damage',['missing','changed','missing-one-reference','directory-symlink','hardlink'])
def test_unverified_or_shared_rollback_never_releases_the_cache(environment,tmp_path,damage):
    st=environment[0].state.store;live,saved=fixture(tmp_path,st,2)
    target=saved[0]/'loader.jar'
    if damage in ['missing','missing-one-reference']:target.unlink()
    elif damage=='changed':target.write_bytes(b'corrupt old loader!')
    elif damage=='hardlink':target.unlink();os.link(live/'loader.jar',target)
    else:
        target.unlink();saved[0].rmdir()
        try:saved[0].symlink_to(live,target_is_directory=True)
        except OSError:pytest.skip('Directory symlink requires an enabled Windows privilege')
    item=runtime_storage.inventory(tmp_path,st.get('server'))[0]
    assert not item['deletable']
    with pytest.raises(ValueError,match='protected'):runtime_storage.delete(st,tmp_path,item['id'],1)
    assert live.exists()


def test_active_copy_remains_protected_even_with_independent_snapshots(environment,tmp_path):
    st=environment[0].state.store;live,_=fixture(tmp_path,st)
    current={**st.get('server'),'loader_version':'26.3.0.97'};st.set('server',current)
    item=runtime_storage.inventory(tmp_path,current)[0]
    assert item['status']=='active' and not item['deletable']
    with pytest.raises(ValueError,match='protected'):runtime_storage.delete(st,tmp_path,item['id'],1)


def test_copy_removed_after_preview_blocks_delete(environment,tmp_path):
    st=environment[0].state.store;live,saved=fixture(tmp_path,st)
    item=runtime_storage.inventory(tmp_path,st.get('server'))[0]
    preview=runtime_storage.delete(st,tmp_path,item['id'],1)
    (saved[0]/'loader.jar').unlink()
    with pytest.raises(ValueError,match='protected'):runtime_storage.delete(st,tmp_path,item['id'],1,preview['confirmation'])
    assert live.is_dir()

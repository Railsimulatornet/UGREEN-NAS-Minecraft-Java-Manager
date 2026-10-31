import pytest
from mcj.world_operations import retire_import

class State:
    def __init__(self,records):self.records=records
    def get(self,key):assert key=='world_imports';return self.records
    def set(self,key,value):assert key=='world_imports';self.records=value

def test_deleted_import_does_not_reappear_and_unused_cache_is_removed(tmp_path,monkeypatch):
    monkeypatch.setenv('MCJ_LAYOUT','legacy');identifier='a'*64
    folder=tmp_path/'staging/worlds'/identifier;folder.mkdir(parents=True);(folder/'level.dat').write_bytes(b'disposable fixture')
    st=State([{'id':identifier,'name':'DeletedTestWorld'}])
    assert retire_import(st,tmp_path,'DeletedTestWorld')==1
    assert st.records==[] and not folder.exists()
    assert retire_import(st,tmp_path,'DeletedTestWorld')==0

def test_other_import_names_keep_the_shared_content(tmp_path,monkeypatch):
    monkeypatch.setenv('MCJ_LAYOUT','legacy');identifier='b'*64
    folder=tmp_path/'staging/worlds'/identifier;folder.mkdir(parents=True);(folder/'level.dat').write_bytes(b'keep')
    keep={'id':identifier,'name':'OtherWorld'};st=State([{'id':identifier,'name':'DeletedWorld'},keep])
    assert retire_import(st,tmp_path,'DeletedWorld')==1
    assert st.records==[keep] and (folder/'level.dat').read_bytes()==b'keep'

@pytest.mark.parametrize('identifier',['../outside','x'*64])
def test_unsafe_import_reference_is_rejected_without_removing_records(tmp_path,monkeypatch,identifier):
    monkeypatch.setenv('MCJ_LAYOUT','legacy');records=[{'id':identifier,'name':'DeletedWorld'}];st=State(records)
    with pytest.raises(ValueError,match='world_staging_integrity_failed'):retire_import(st,tmp_path,'DeletedWorld')
    assert st.records==records

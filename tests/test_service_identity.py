import pytest
from mcj.service_identity import allocated,validate

def test_existing_uid_1009_and_group_10_are_never_selected():
    uid,gid=allocated('root:x:0:0::/:/bin/sh\nrealperson:x:1009:10::/:/bin/sh','users:x:10:')
    assert 200000<=uid<300000 and uid==gid and uid!=1009 and gid!=10

@pytest.mark.parametrize('where',['user','group','primary_group','container'])
def test_restart_refuses_new_host_account_or_foreign_container_collision(where):
    p='other:x:240001:20::/:/bin/sh' if where=='user' else 'other:x:1500:240002::/:/bin/sh' if where=='primary_group' else 'root:x:0:0::/:/bin/sh'
    g='other:x:240002:' if where=='group' else 'root:x:0:'
    reserved=[240001] if where=='container' else []
    with pytest.raises(ValueError,match='collision'):allocated(p,g,reserved,(240001,240002))

def test_same_checked_unused_identity_is_kept_and_root_or_boolean_refused():
    assert allocated('root:x:0:0::/:/bin/sh','root:x:0:',previous=(240001,240002))==(240001,240002)
    for pair in [(0,10),(1009,0),(True,10),(-1,10)]:
        with pytest.raises(ValueError):validate(*pair)

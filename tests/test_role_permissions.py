import json
import pytest
from mcj import role_permissions as permissions
from mcj.project_paths import project_path


def test_default_groups_do_not_grant_op_or_visitor_abilities():
    value=permissions.defaults()
    assert value['visitor']==value['player']==[]
    assert value['moderator']==['kick','announce']
    assert set(value['administrator'])==set(permissions.ABILITIES)
    assert permissions.normalize(value)==value


@pytest.mark.parametrize('changed',[
    {'visitor':['kick']},{'moderator':['op']},{'player':['kick','kick']},{'player':'kick'},
    {'administrator':['kick','announce','time','weather','execute']},{'unknown':[]},{'moderator':[True]}])
def test_arbitrary_commands_op_visitor_grants_and_invalid_shapes_are_denied(changed):
    with pytest.raises(ValueError,match='invalid_role_permissions|visitor_permissions_are_fixed'):
        permissions.normalize({**permissions.defaults(),**changed})


@pytest.mark.parametrize('layout',['legacy','services-v1'])
def test_configuration_roundtrip_is_explicit_and_requires_no_server_restart(tmp_path,monkeypatch,layout):
    monkeypatch.setenv('MCJ_LAYOUT',layout)
    assert not permissions.read(tmp_path)['configured']
    value=permissions.defaults();value['moderator']=['announce']
    permissions.write(tmp_path,value)
    assert permissions.read(tmp_path)['roles']==value and permissions.read(tmp_path)['configured']
    path=project_path(tmp_path,'control/roles/permissions.json');path.write_text('{')
    with pytest.raises(ValueError,match='invalid_role_permissions'):permissions.read(tmp_path)
    path.write_text(json.dumps({'format':2,'roles':value}))
    with pytest.raises(ValueError,match='invalid_role_permissions'):permissions.read(tmp_path)


def test_changed_trusted_guard_invalidates_pending_mod_and_version_approvals(tmp_path):
    from cryptography.fernet import Fernet
    from mcj.store import Store
    from mcj.mods import fingerprint
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());st=Store(tmp_path/'state',key)
    st.set('guard_catalog',{'artifacts':[{'sha256':'1'*64,'minecraft':'26.3','loader':'NEOFORGE'}]})
    before=fingerprint(st)
    st.set('guard_catalog',{'artifacts':[{'sha256':'2'*64,'minecraft':'26.3','loader':'NEOFORGE'}]})
    assert fingerprint(st)!=before

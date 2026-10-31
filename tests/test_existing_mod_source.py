"""Link a verified provider selection to the same existing immutable mod."""
import json
import pytest
from mcj import mods,sources
from test_security import environment,jar

def fixture(st,root,*,source='upload',origin=None):
    raw=jar({'fabric.mod.json':json.dumps({'id':'source_fixture','version':'1.0','depends':{'minecraft':'26.3'}})})
    row=mods.stage(st,root,raw,'source-fixture.jar',source)
    with st.db() as db:
        db.execute("UPDATE mods SET state='installed',enabled=0,installed_enabled=1,origin=?,available=? WHERE id=?",
                   (json.dumps(origin) if origin else None,json.dumps({'status':'unknown_source','version':None}),row['id']))
    prepared={**row,'sha256':row['id'],'source':'curseforge',
              'origin':{'provider':'curseforge','project_id':123,'file_id':456,'url':'https://www.curseforge.com/minecraft/mc-mods/source-fixture','pinned':False}}
    return row,prepared

def test_verified_selection_links_exact_uploaded_mod_without_reinstall_or_desired_change(environment):
    app,_,_,_=environment;st=app.state.store
    row,prepared=fixture(st,st.state.parent)
    staging=st.state.parent/'staging'/(row['id']+'.jar');original=staging.read_bytes()
    with st.db() as db:before=dict(db.execute('SELECT * FROM mods WHERE id=?',(row['id'],)).fetchone())
    result=sources.register_prepared(st,[prepared])
    with st.db() as db:after=dict(db.execute('SELECT * FROM mods WHERE id=?',(row['id'],)).fetchone())
    assert json.loads(after['origin'])==prepared['origin']
    assert after['source']=='curseforge' and after['available'] is None
    assert staging.read_bytes()==original
    for key in ('id','sha256','filename','metadata','state','enabled','installed_enabled','remove_pending','replaces'):
        assert after[key]==before[key]
    assert result==[{'id':row['id'],'already_present':True,'enabled':False,'installed':True,'source_linked':True}]

@pytest.mark.parametrize('source,origin',[
    ('system',None),
    ('upload',{'provider':'manual_patch','url':'https://www.curseforge.com/minecraft/mc-mods/source-fixture'}),
    ('curseforge',{'provider':'curseforge','project_id':123,'file_id':456,'pinned':True}),
])
def test_existing_protection_patch_and_provider_choice_are_preserved(environment,source,origin):
    app,_,_,_=environment;st=app.state.store
    row,prepared=fixture(st,st.state.parent,source=source,origin=origin)
    with st.db() as db:before=dict(db.execute('SELECT * FROM mods WHERE id=?',(row['id'],)).fetchone())
    result=sources.register_prepared(st,[prepared])
    with st.db() as db:after=dict(db.execute('SELECT * FROM mods WHERE id=?',(row['id'],)).fetchone())
    assert before==after
    assert not result[0].get('source_linked') and result[0]['already_present']

import json,time
from mcj import sources
from test_security import environment,enroll

def test_source_inventory_separates_metadata_pending_and_active_without_claiming_test_pass(environment):
    app,client,_,_=environment;enroll(environment);st=app.state.store
    url='https://www.curseforge.com/minecraft/mc-mods/carry-on'
    source={**sources.reference(url),'report':{'state':'metadata_checked','runtime_test':'not_tested'}}
    st.set('mod_sources',[source])
    with st.db() as db:
        for index,state,active,origin in [(1,'installed',1,{'provider':'manual_patch','url':url}),(2,'staged',0,{'provider':'curseforge','url':url}),(3,'superseded',0,{'provider':'curseforge','url':url}),(4,'installed',0,{'provider':'curseforge','url':url+'/files/1234'})]:
            identifier=str(index)*64
            db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,installed_enabled,origin,updated) VALUES(?,?,?,?,?,?,?,?,?)',(identifier,str(index)+'.jar',identifier,'{}','upload',state,active,json.dumps(origin),time.time()))
    result=client.get('/api/mods/sources').json()['sources'][0]
    assert result['report']['runtime_test']=='not_tested'
    assert result['installation']=={'active':['1.jar'],'inactive':['4.jar'],'pending':['2.jar'],'locally_modified':True}
    # Read-time decoration must not rewrite persistent provider reports.
    assert 'installation' not in st.get('mod_sources')[0]

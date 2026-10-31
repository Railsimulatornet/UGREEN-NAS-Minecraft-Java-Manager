import io,json,time,zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_security import environment,enroll,post
from mcj import mods,maintenance,versions,packs,worlds


def row(st,identifier='a',enabled=1,installed=1,source='upload'):
 key=identifier*64;meta={'mods':[{'id':'fixture_'+identifier,'version':'1','name':'Fixture'}],'dependencies':[],'embedded':[]}
 with st.db() as db:db.execute("INSERT INTO mods(id,filename,sha256,metadata,source,state,enabled,installed_enabled,updated) VALUES(?,?,?,?,?,'installed',?,?,?)",(key,'fixture_'+identifier+'.jar',key,json.dumps(meta),source,enabled,installed,time.time()))
 return key


@pytest.mark.parametrize('enabled',[0,1])
def test_uninstall_stages_and_cancel_restores_desired_state(environment,enabled):
 app,client,creds,mail=environment;csrf=enroll(environment)['csrf'];st=app.state.store;key=row(st,enabled=enabled)
 before=mods.fingerprint(st)
 result=post(client,f'/api/mods/{key}/removal',{'remove':True},csrf);assert result.status_code==200
 with st.db() as db:r=dict(db.execute('SELECT * FROM mods WHERE id=?',(key,)).fetchone())
 assert r['remove_pending']==enabled and r['enabled']==0 and r['installed_enabled']==1 and r['state']=='installed'
 assert mods.fingerprint(st)!=before
 assert post(client,f'/api/mods/{key}/desired',{'enabled':True},csrf).status_code==409
 assert post(client,f'/api/mods/{key}/update',{},csrf).status_code==409
 with pytest.raises(ValueError,match='mod_removal_pending'):mods.stage_modrinth_update(st,app.state.root if hasattr(app.state,'root') else None,key)
 assert post(client,f'/api/mods/{key}/removal',{'remove':True},csrf).status_code==200
 assert post(client,f'/api/mods/{key}/removal',{'remove':False},csrf).status_code==200
 with st.db() as db:r=dict(db.execute('SELECT * FROM mods WHERE id=?',(key,)).fetchone())
 assert r['remove_pending'] is None and r['enabled']==enabled and r['installed_enabled']==1
 assert mods.fingerprint(st)==before


def test_uninstall_requires_admin_csrf_and_protects_guard_pending_update(environment):
 app,client,creds,mail=environment;csrf=enroll(environment)['csrf'];st=app.state.store;key=row(st,source='system')
 assert post(client,f'/api/mods/{key}/removal',{'remove':True},csrf).status_code==409
 other=row(st,'b');assert post(client,f'/api/mods/{other}/removal',{'remove':True}).status_code==403
 update=row(st,'c')
 with st.db() as db:db.execute("UPDATE mods SET state='staged',replaces=? WHERE id=?",(other,update))
 assert post(client,f'/api/mods/{other}/removal',{'remove':True},csrf).status_code==409
 with st.db() as db:db.execute('UPDATE users SET admin=0 WHERE id=1')
 assert post(client,f'/api/mods/{other}/removal',{'remove':True},csrf).status_code==403


def test_update_search_state_is_separate_from_installed_enabled_and_system_management(environment):
 app,client,creds,mail=environment;enroll(environment);st=app.state.store
 guard=row(st,source='system');regular=row(st,'b')
 with st.db() as db:
  for record in db.execute('SELECT id,metadata FROM mods').fetchall():
   meta=json.loads(record['metadata']);meta.update(loader=st.get('server')['loader'],client_only_hint=False)
   db.execute('UPDATE mods SET metadata=? WHERE id=?',(json.dumps(meta),record['id']))
 records={r['id']:r for r in client.get('/api/mods').json()['mods']}
 assert records[guard]['available']=={'status':'system_managed','version':'1'}
 assert records[guard]['protected'] and records[guard]['installed_enabled']
 assert records[regular]['available']['status']=='not_checked'
 assert records[regular]['state']=='installed' and records[regular]['installed_enabled']


@pytest.mark.parametrize('include_pending',[True,False])
def test_candidate_removes_only_explicit_uninstall_not_normal_disabled_mod(tmp_path,monkeypatch,include_pending):
 scratch=tmp_path/'candidate';data=scratch/'data';data.mkdir(parents=True)
 (scratch/'runtime.json').write_text(json.dumps({'version':'26.3','loader':'NEOFORGE'}))
 guard=tmp_path/'guard.jar';out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:z.writestr('fabric.mod.json',json.dumps({'id':'fixture','version':'1'}))
 raw=out.getvalue();guard.write_bytes(raw)
 rows=[{'id':'a'*64,'sha256':'a'*64,'state':'installed','filename':'removed.jar','enabled':0,'installed_enabled':1,'source':'upload','metadata':{},'remove_pending':1},{'id':'b'*64,'sha256':'b'*64,'state':'installed','filename':'disabled.jar','enabled':0,'installed_enabled':0,'source':'upload','metadata':{},'remove_pending':None}]
 monkeypatch.setattr(maintenance,'store',lambda c:SimpleNamespace(get=lambda key:{}))
 monkeypatch.setattr(versions,'ensure_runtime_components',lambda st,value:value)
 copied=[]
 monkeypatch.setattr(maintenance,'staged_bytes',lambda c,r:(copied.append(r['filename']) or raw))
 monkeypatch.setattr(maintenance,'safe_remove',lambda *a:None)
 monkeypatch.setattr(packs,'apply_pending',lambda *a:{})
 monkeypatch.setattr(worlds,'apply_import',lambda *a:None)
 class ReachedDependencies(Exception):pass
 def check(rows,runtime):raise ReachedDependencies()
 monkeypatch.setattr(mods,'dependency_report',check)
 controller=SimpleNamespace(ROOT=tmp_path,extract_archive=lambda p:(scratch,data,{},None),trusted_guard=lambda *a:{'sha256':'g'*64,'filename':'guard.jar','path':'guard.jar'})
 with pytest.raises(ReachedDependencies):maintenance.candidate(controller,{'path':'fixture'},{},'unused',records=rows,include_pending=include_pending)
 assert copied==(['disabled.jar'] if include_pending else ['removed.jar','disabled.jar'])
 assert (data/'mods-disabled'/('b'*64+'.jar')).read_bytes()==raw
 assert (data/'mods-disabled'/('a'*64+'.jar')).exists()==(not include_pending)

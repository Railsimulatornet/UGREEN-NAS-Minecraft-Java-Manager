import pytest
from mcj import memory_budget
from mcj.server_settings import normalize
from test_security import environment,enroll,post

def test_total_16g_selects_14g_java_and_preserves_standard_existing_limit():
    current={'version':'26.3','memory_mb':6144,'world':'world','properties':{}}
    selected=normalize(current,{'container_memory_mb':16384})
    assert selected['container_memory_mb']==16384 and selected['memory_mb']==14336
    assert memory_budget.limits(current)==(8192,6144)
    assert current['memory_mb']==6144

@pytest.mark.parametrize('change',[{'container_memory_mb':True},{'container_memory_mb':3072},{'container_memory_mb':8193},{'container_memory_mb':66560},{'container_memory_mb':16384,'memory_mb':16384},{'memory_mb':0},{'memory_mb':True}])
def test_invalid_limits_or_heap_without_reserve_are_rejected(change):
    with pytest.raises(ValueError):normalize({'version':'26.3','memory_mb':6144},change)

def test_preflight_reclaims_only_actual_container_usage_and_keeps_nas_reserve():
    gib=1024**3;cfg={'container_memory_mb':16384,'memory_mb':14336}
    good=memory_budget.require(cfg,{'MemTotal':64*gib,'MemAvailable':24*gib},6*gib)
    assert good['sufficient'] and good['host_reserve_mb']>=6553
    with pytest.raises(ValueError,match='insufficient_host_memory'):
        memory_budget.require(cfg,{'MemTotal':16*gib,'MemAvailable':12*gib},6*gib)
    with pytest.raises(ValueError,match='insufficient_host_memory'):
        memory_budget.require(cfg,{'MemTotal':64*gib,'MemAvailable':4*gib},6*gib)

def test_read_host_memory_uses_available_not_free(tmp_path):
    p=tmp_path/'meminfo';p.write_text('MemTotal: 67108864 kB\nMemAvailable: 25165824 kB\nMemFree: 1000 kB\n')
    assert memory_budget.host_memory(p)=={'MemTotal':64*1024**3,'MemAvailable':24*1024**3}
    p.write_text('MemTotal: 67108864 kB\n')
    with pytest.raises(ValueError):memory_budget.host_memory(p)

def test_memory_change_is_staged_as_a_real_settings_job(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    response=post(client,'/api/jobs',{'kind':'server_settings','mode':'manual','approved':False,'payload':{'changes':{'container_memory_mb':16384}}},csrf)
    assert response.status_code==200
    import json
    with app.state.store.db() as db:row=db.execute('SELECT * FROM jobs WHERE id=?',(response.json()['id'],)).fetchone()
    assert row['state']=='planned'
    cfg=json.loads(row['payload'])['configuration'];assert cfg['container_memory_mb']==16384 and cfg['memory_mb']==14336
    assert app.state.store.get('server')['memory_mb']==6144

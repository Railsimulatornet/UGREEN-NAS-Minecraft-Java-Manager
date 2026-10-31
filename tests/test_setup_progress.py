import json,sys
from pathlib import Path
import pytest
from mcj import bootstrap

@pytest.mark.parametrize('phase,completed',[('ready',0),('checking',0),('folders',1),('runtime',2),('account',3),('starting',4),('handover',5),('complete',6)])
def test_counts_only_completed_real_stages(phase,completed):
    assert bootstrap.step_progress(phase)=={'completed':completed,'total':6}

def test_failure_retains_last_real_progress_and_never_claims_completion(tmp_path,monkeypatch):
    sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
    import bootstrap_worker
    writes=[]
    def atomic(path,raw,*args,**kwargs):
        writes.append(json.loads(raw));path.write_bytes(raw)
    monkeypatch.setattr(bootstrap,'atomic',atomic)
    bootstrap_worker.status(tmp_path,'starting')
    bootstrap_worker.status(tmp_path,'failed',error='setup_failed_fixture')
    assert writes[-1]['progress']=={'completed':4,'total':6}
    for unsafe in [{'completed':True},{'completed':-1},{'completed':6.5},{'completed':100}]:
        assert bootstrap.step_progress('failed',unsafe)['completed']==0

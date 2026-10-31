import json,os
from types import SimpleNamespace
from mcj.job_control import deployment_held


def test_lease_pauses_worker_only_for_a_bounded_window(tmp_path):
    store=SimpleNamespace(state=tmp_path);path=tmp_path/'.deployment-hold.json';now=1700000000
    assert deployment_held(store,now) is False
    path.write_text(json.dumps({'until':now+180}));os.utime(path,(now,now))
    assert deployment_held(store,now) is True
    assert deployment_held(store,now+181) is False
    path.write_text(json.dumps({'until':now+999999}));os.utime(path,(now,now))
    assert deployment_held(store,now) is True
    assert deployment_held(store,now+301) is False


def test_corrupt_or_expired_lease_cannot_permanently_block_jobs(tmp_path):
    store=SimpleNamespace(state=tmp_path);path=tmp_path/'.deployment-hold.json';now=1700000000
    for raw in ['{broken','[]','null','x'*1025,json.dumps({'until':True})]:
        path.write_text(raw);os.utime(path,(now,now))
        assert deployment_held(store,now) is True
        assert deployment_held(store,now+301) is False
    path.write_text(json.dumps({'until':now-1}));os.utime(path,(now,now))
    assert deployment_held(store,now) is False

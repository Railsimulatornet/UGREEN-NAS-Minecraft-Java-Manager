import hashlib,json
from pathlib import Path
import pytest
from mcj import guard_bundle


def fixture(tmp_path):
    directory=tmp_path/'image-artifacts';directory.mkdir()
    records=[]
    for version,java in [('26.3',25),('1.21.1',21)]:
        raw=('test-only-'+version).encode();filename='guard-'+version+'.jar'
        (directory/filename).write_bytes(raw)
        record={'minecraft':version,'loader':'NEOFORGE','java':java,'version':'1.0.5','filename':filename,
                'sha256':hashlib.sha256(raw).hexdigest(),'dependencies':[],'visitor_verified':False,
                'visitor_client_test':'not_verified_for_this_artifact','runtime_test':'not_tested'}
        (directory/('guard-'+version+'.json')).write_text(json.dumps(record));records.append(record)
    (directory/'catalog.json').write_text(json.dumps({'manifests':['guard-26.3.json','guard-1.21.1.json']}))
    return directory,records


def test_publishing_candidates_keeps_live_guard_and_existing_roles_unchanged(tmp_path,monkeypatch):
    monkeypatch.setenv('MCJ_LAYOUT','legacy');directory,records=fixture(tmp_path)
    root=tmp_path/'project';registry=root/'releases/guards/registry.json';registry.parent.mkdir(parents=True)
    old={'minecraft':'26.3','loader':'NEOFORGE','filename':'previous.jar','sha256':'a'*64,'path':'releases/guards/previous.jar'}
    registry.write_text(json.dumps({'artifacts':[old]}))
    roles=root/'control/roles/roles.json';roles.parent.mkdir(parents=True);roles.write_text('{"retained-role":true}')
    live=root/'server/mods/previous.jar';live.parent.mkdir(parents=True);live.write_bytes(b'unchanged-live-artifact')
    assert guard_bundle.install_registry(root,directory)
    value=json.loads(registry.read_text());assert len(value['artifacts'])==2
    assert value['retained_artifacts']==[old]
    assert all(x['visitor_verified'] is False for x in value['artifacts'])
    assert {x['java'] for x in value['artifacts']}=={21,25}
    assert roles.read_text()=='{"retained-role":true}' and live.read_bytes()==b'unchanged-live-artifact'
    before=registry.read_bytes();assert guard_bundle.install_registry(root,directory)
    assert registry.read_bytes()==before


@pytest.mark.parametrize('problem',['manifest_traversal','artifact_changed','unsupported','wrong_java','duplicate'])
def test_untrusted_bundle_never_replaces_the_registry(tmp_path,monkeypatch,problem):
    monkeypatch.setenv('MCJ_LAYOUT','legacy');directory,records=fixture(tmp_path)
    root=tmp_path/'project';registry=root/'releases/guards/registry.json';registry.parent.mkdir(parents=True)
    registry.write_text('{"artifacts":[]}');original=registry.read_bytes()
    if problem=='manifest_traversal':(directory/'catalog.json').write_text('{"manifests":["../outside.json"]}')
    elif problem=='artifact_changed':(directory/records[0]['filename']).write_bytes(b'changed')
    else:
        if problem=='unsupported':records[0]['minecraft']='1.20.1'
        elif problem=='wrong_java':records[0]['java']=21
        elif problem=='duplicate':records[1].update(minecraft='26.3',java=25)
        for i,version in enumerate(['26.3','1.21.1']):(directory/('guard-'+version+'.json')).write_text(json.dumps(records[i]))
    with pytest.raises(RuntimeError):guard_bundle.install_registry(root,directory)
    assert registry.read_bytes()==original


def test_existing_destination_is_never_silently_overwritten(tmp_path,monkeypatch):
    monkeypatch.setenv('MCJ_LAYOUT','legacy');directory,records=fixture(tmp_path)
    root=tmp_path/'project';registry=root/'releases/guards/registry.json';registry.parent.mkdir(parents=True)
    registry.write_text('{"artifacts":[]}')
    destination=registry.parent/'neoforge-26.3'/records[0]['filename'];destination.parent.mkdir();destination.write_bytes(b'different')
    with pytest.raises(RuntimeError,match='integrity'):guard_bundle.install_registry(root,directory)
    assert destination.read_bytes()==b'different' and json.loads(registry.read_text())=={'artifacts':[]}


def test_shipped_acceptance_is_bound_to_the_exact_unchanged_artifacts():
    directory=Path(__file__).resolve().parents[1]/'artifacts'
    record_path=directory/'guard-acceptance-20261031.json';raw=record_path.read_bytes();record=json.loads(raw)
    assert record['decision']=='accepted_for_exact_configurations_and_mod_inventory' and not record['guard_jars_changed']
    catalogue=guard_bundle.read(directory)
    assert len(catalogue['artifacts'])==len(record['configurations'])==2
    for entry in catalogue['artifacts']:
        scope=next(x for x in record['configurations'] if x['minecraft']==entry['minecraft'])
        assert entry['visitor_verified'] is True and entry['visitor_client_test']=='passed'
        assert entry['acceptance']['sha256']==hashlib.sha256(raw).hexdigest()
        assert scope['guard_sha256']==entry['sha256']==hashlib.sha256((directory/entry['filename']).read_bytes()).hexdigest()
        assert scope['loader_version'] in entry['tested_loaders'] and scope['java']==entry['java']
        assert scope['decision']=='passed_for_fixed_scope' and scope['operator'] is False
        assert scope['client_cases'] and all(x['result']=='passed' and x['guard_sha256']==entry['sha256'] for x in scope['client_cases'])

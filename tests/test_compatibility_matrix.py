from mcj.compatibility import matrix
from types import SimpleNamespace

def test_source_folders_and_official_catalogues_are_not_support_evidence():
    data={'artifacts':[{'minecraft':'26.3','loader':'NEOFORGE','version':'1.0.5','sha256':'a'*64,'runtime_test':'passed','tested_loaders':['26.3.0.99'],'visitor_client_test':'not_verified_for_this_artifact'}]}
    view=matrix(SimpleNamespace(get=lambda key:data))
    assert view['single_instance_per_nas'] is True
    assert len(view['variants'])==1 and view['variants'][0]['loader_versions']==['26.3.0.99']
    assert view['variants'][0]['visitor_client_test']=='not_verified_for_this_artifact'
    assert view['variants'][0]['selectable'] is False
    assert {'FORGE','VANILLA','PAPER','SPIGOT','QUILT','BEDROCK'}<=set(view['unsupported'])

def test_legacy_catalogue_without_specific_runtime_tests_has_no_selectable_versions():
    view=matrix(SimpleNamespace(get=lambda key:{'artifacts':[{'minecraft':'26.3','loader':'FABRIC','sha256':'a'*64}]}))
    assert not view['variants'][0]['loader_versions'] and view['variants'][0]['runtime_test']=='not_tested'


def test_packaged_adapters_keep_their_own_java_channel():
    from mcj.guard_bundle import read
    view=matrix(SimpleNamespace(get=lambda key:read()))
    assert len(view['variants'])==9
    assert {(x['minecraft'],x['loader'],x['java']) for x in view['variants']}=={
        (minecraft,loader,java) for minecraft,java in [('1.20.1',17),('1.21.1',21),('26.3',25)]
        for loader in ['FABRIC','FORGE','NEOFORGE']}
    accepted={(x['minecraft'],x['loader']) for x in read()['artifacts']
              if x.get('visitor_verified') and x.get('visitor_client_test')=='passed'}
    assert {(x['minecraft'],x['loader']) for x in view['variants'] if x['selectable']}==accepted
    assert all(x['runtime_test']=='passed' and x['visitor_client_test']=='passed' for x in view['variants'] if x['selectable'])
    assert all(not x['loader_versions'] for x in view['variants'] if not x['selectable'])


def test_release_scope_is_actually_selectable_with_exact_tested_loader_versions():
    import hashlib,json
    from pathlib import Path
    from mcj.guard_bundle import read
    root=Path(__file__).resolve().parents[1]
    evidence=json.loads((root/'artifacts/compatibility/release-matrix.json').read_text())
    expected={(x['minecraft'],x['loader'],x['java'],x['loader_version'],x['guard']['sha256'])
              for x in evidence['entries'] if x['status']=='BESTANDEN'}
    view=matrix(SimpleNamespace(get=lambda key:read()))
    actual={(x['minecraft'],x['loader'],x['java'],version,x['guard_sha256'])
            for x in view['variants'] if x['selectable'] for version in x['loader_versions']}
    assert len(expected)==9 and actual==expected
    for entry in read()['artifacts']:
        acceptance=entry['acceptance'];record=root/acceptance['scope']
        assert hashlib.sha256(record.read_bytes()).hexdigest()==acceptance['sha256']
    assert {'VANILLA','PAPER','SPIGOT','QUILT','BEDROCK'}<=set(view['unsupported'])

from mcj.compatibility import matrix
from types import SimpleNamespace

def test_source_folders_and_official_catalogues_are_not_support_evidence():
    data={'artifacts':[{'minecraft':'26.3','loader':'NEOFORGE','version':'1.0.5','sha256':'a'*64,'runtime_test':'passed','tested_loaders':['26.3.0.99'],'visitor_client_test':'not_verified_for_this_artifact'}]}
    view=matrix(SimpleNamespace(get=lambda key:data))
    assert view['single_instance_per_nas'] is True
    assert len(view['variants'])==1 and view['variants'][0]['loader_versions']==['26.3.0.99']
    assert view['variants'][0]['visitor_client_test']=='not_verified_for_this_artifact'
    assert {'FORGE','VANILLA','PAPER','SPIGOT','QUILT','BEDROCK'}<=set(view['unsupported'])

def test_legacy_catalogue_without_specific_runtime_tests_has_no_selectable_versions():
    view=matrix(SimpleNamespace(get=lambda key:{'artifacts':[{'minecraft':'26.3','loader':'FABRIC','sha256':'a'*64}]}))
    assert not view['variants'][0]['loader_versions'] and view['variants'][0]['runtime_test']=='not_tested'


def test_packaged_adapters_keep_their_own_java_channel():
    from mcj.guard_bundle import read
    view=matrix(SimpleNamespace(get=lambda key:read()))
    assert {(x['minecraft'],x['loader'],x['java']) for x in view['variants']}=={('26.3','NEOFORGE',25),('1.21.1','NEOFORGE',21)}
    # Only the two shipped adapters have the revision-bound client acceptance.
    # Unverified fixture catalogues above must retain their original state.
    assert all(x['runtime_test']=='passed' and x['visitor_client_test']=='passed' for x in view['variants'])

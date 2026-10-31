from mcj.mods import dependency_report

SERVER={'version':'26.3','loader':'FABRIC','loader_version':'0.20.1','java':25}
def metadata(identifier,version,embedded=(),dependencies=()):
    import hashlib
    return {'loader':'FABRIC','mods':[{'id':identifier,'version':version}],'dependencies':list(dependencies),
            'embedded':list(embedded),'environment':'*','client_only_hint':False,'provides':[],
            'sha256':hashlib.sha256((identifier+version).encode()).hexdigest()}
def record(meta):return {'id':meta['sha256'],'metadata':meta}
def require(identifier,predicate):return {'id':identifier,'range':predicate,'mandatory':True}

def test_nested_library_candidates_are_not_duplicate_top_level_mods():
    old=metadata('shared_library','1.0.0');new=metadata('shared_library','2.0.0')
    first=metadata('first_mod','1.0.0',[old],[require('shared_library','>=1.0')])
    second=metadata('second_mod','1.0.0',[new],[require('shared_library','>=2.0')])
    result=dependency_report([record(first),record(second)],SERVER)
    assert result['structural_checks']=='passed' and result['version_range_checks']=='passed'
    assert result['nested_resolution'][0]['preflight_version']=='2.0.0'
    assert result['nested_resolution'][0]['native_loader_test_required'] is True
    assert result['runtime_compatibility']=='unverified'

def test_unsatisfied_nested_constraints_stay_blocked():
    inner=metadata('shared_library','1.0.0')
    parent=metadata('parent_mod','1.0.0',[inner],[require('shared_library','>=2.0')])
    result=dependency_report([record(parent)],SERVER)
    assert result['structural_checks']=='failed' and result['version_range_checks']=='unverified'

def test_two_top_level_versions_remain_a_definite_conflict():
    result=dependency_report([record(metadata('same_mod','1.0.0')),record(metadata('same_mod','2.0.0'))],SERVER)
    assert any(x['issue']=='duplicate_mod_id' for x in result['issues'])

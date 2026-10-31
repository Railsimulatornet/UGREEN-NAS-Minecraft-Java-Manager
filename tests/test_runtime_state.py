from mcj.runtime_state import compare

def test_outdated_forge_metadata_cannot_claim_current_fabric_configuration():
    database={'version':'1.20.1','loader':'FORGE','loader_version':'47.4.28'}
    actual={'version':'26.3','java':25,'loader':'FABRIC','loader_version':'0.20.1'}
    assert compare(database,actual)['state']=='unverified'
    database['java']=25
    result=compare(database,actual)
    assert result=={'state':'mismatch','different_fields':['version','loader','loader_version']}
    assert compare(actual,actual)=={'state':'consistent','different_fields':[]}
    assert compare(actual,None)['state']=='unverified'

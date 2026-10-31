import json
from cryptography.fernet import Fernet
import pytest
from mcj.mods import trial_report
from mcj.store import Store


def test_retained_server_test_never_claims_client_or_visitor_acceptance(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    store=Store(tmp_path/'state',key)
    assert trial_report(store) is None
    evidence={'checked_at':1792859941,'basis':store.get('server'),'results':[
        {'name':'Carry On','source_url':'https://www.curseforge.com/minecraft/mc-mods/carry-on',
         'status':'isolated_start_passed','versions':[{'version':'2.12.0'}],'prerelease':False,
         'operator_internal_field':'must not be served'}],
        'combined':{'state':'isolated_start_passed'},'visitor_permissions_with_extra_mods_tested':True}
    store.atomic(store.state/'requested-mod-test-results.json',json.dumps(evidence).encode())
    result=trial_report(store)
    assert result['basis_matches_configuration'] and result['combined_start_passed']
    assert result['client_interactions_tested'] is False
    assert result['visitor_permissions_with_extra_mods_tested'] is False
    assert result['installation_approved'] is False
    assert 'operator_internal_field' not in result['results'][0]
    store.set('server',{**store.get('server'),'version':'26.4'})
    assert trial_report(store)['basis_matches_configuration'] is False
    assert not (tmp_path/'server').exists()


@pytest.mark.parametrize('content',[
    b'not json',b'{"checked_at":0,"basis":{},"results":[]}',b'X'*(1024*1024+1),
    b'{"checked_at":0,"basis":{},"results":[{"source_url":"javascript:alert(1)"}]}'],
    ids=['malformed-json','missing-basis','oversized','unsafe-link'])
def test_malformed_or_oversized_retained_report_is_rejected(tmp_path,content):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    store=Store(tmp_path/'state',key)
    store.atomic(store.state/'requested-mod-test-results.json',content)
    with pytest.raises(ValueError):trial_report(store)

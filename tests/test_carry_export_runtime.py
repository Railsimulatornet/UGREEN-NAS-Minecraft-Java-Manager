import pytest
from mcj import client_packs as cp


@pytest.mark.parametrize('version',['26.3.0.97','26.3.0.99'])
def test_exact_carry_patch_is_included_on_both_observed_client_runtimes(version):
    record={'hashes':{'sha256':cp.CARRY_HASH},'source':'upload','metadata':{'mods':[{'id':'carryon'}]}}
    result=cp.classify(None,record,{'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':version})
    assert result['client']=='required' and result['embedded_patch'] and result['license']=='LGPL-3.0-or-later'


@pytest.mark.parametrize('changed',[{'loader_version':'26.3.0.100'},{'version':'26.4'},{'java':21},{'loader':'FABRIC'},{'hash':'0'*64}])
def test_an_unobserved_runtime_or_different_patch_is_not_silently_approved(monkeypatch,changed):
    active={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.99',**{k:v for k,v in changed.items() if k!='hash'}}
    record={'hashes':{'sha256':changed.get('hash',cp.CARRY_HASH)},'source':'upload','metadata':{'mods':[{'id':'carryon'}]}}
    monkeypatch.setattr(cp,'modrinth_record',lambda *_:None);monkeypatch.setattr(cp,'curseforge_record',lambda *_:None)
    assert cp.classify(None,record,active)=={'client':'unknown','reason':'client_requirements_unknown'}


def test_changed_export_policy_invalidates_archives_built_with_old_selection_rules(monkeypatch):
    active={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.99'}
    previous=cp.fingerprint(active,[])
    monkeypatch.setattr(cp,'EXPORT_POLICY','another-reviewed-policy')
    assert previous!=cp.fingerprint(active,[])

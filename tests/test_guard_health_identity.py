import pytest
from mcj.guard_health import verified,LEGACY_REPORTERS

def test_current_build_and_protocol_must_both_match():
    artifact={'version':'1.0.5','sha256':'b'*64}
    report={'guard_version':'1.0.5','guard_protocol':1,'online_mode':True,'at':100}
    assert verified(report,artifact,now=105)
    for changed in ({'guard_version':'1.0.0'},{'guard_version':'1.0.4'},{'guard_protocol':2},{'guard_protocol':True},{'online_mode':False},{'at':float('nan')},{'at':80},{'at':110}):
        assert not verified({**report,**changed},artifact,now=105)

def test_legacy_reporting_requires_the_exact_previous_artifact():
    sha,version=next(iter(LEGACY_REPORTERS.items()))
    old={'guard_version':'1.0.0','online_mode':True,'at':100}
    assert verified(old,{'version':version,'sha256':sha},now=101)
    assert not verified(old,{'version':version,'sha256':'c'*64},now=101)
    assert not verified(old,{'version':'1.0.5','sha256':sha},now=101)
    assert not verified(old,{},now=101)

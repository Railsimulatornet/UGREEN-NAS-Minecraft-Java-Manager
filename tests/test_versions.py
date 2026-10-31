import pytest
from mcj.version_ranges import matches

@pytest.mark.parametrize('version,predicate,expected',[
 ('26.3','26.3',True),('26.3','1.20.1',False),('26.3.0','26.3',True),
 ('26.3','>=26.1 <26.4',True),('26.4','>=26.1 <26.4',False),
 ('25.0.4.1','>=25',True),('21.0.9','>=25',False),
 ('0.20.1','>=0.20.1',True),('0.19.5','>=0.20.1',False),
 ('26.3','26.x',True),('26.3.1','26.3.*',True),('26.4','26.3.x',False),
 ('26.3','~26.3',True),('26.4-rc.1','~26.3',False),
 ('0.9','^0.2.3',True),('1.0','^0.2.3',False),
 ('1.2.3+build.3','1.2.3+build.4',True),('1.2.3-rc.1','>=1.2.3',False),
 ('1.2.3-rc.2','>1.2.3-rc.1',True),('release-name','release-name',True),
 ('26.3',['1.20.1','26.3'],True),('26.3',['1.20.1','26.2'],False),
 ('26.3','[26.1,26.4)',None),('26.3',{},None),('26.3',[],None),
])
def test_fabric_dependency_predicates(version,predicate,expected):
    assert matches(version,predicate) is expected

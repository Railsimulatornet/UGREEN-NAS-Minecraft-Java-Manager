"""Conservative Fabric metadata predicates. None means an unsupported predicate, never approval."""
from functools import total_ordering
import re

@total_ordering
class Version:
    def __init__(self,value):
        match=re.fullmatch(r'(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]*))?(?:\+[0-9A-Za-z.-]+)?',value)
        if not match:raise ValueError('non_semantic_version')
        self.numbers=tuple(int(x) for x in match[1].split('.'))
        self.pre=None if match[2] is None else tuple(match[2].split('.'))

    def compare(self,other):
        count=max(len(self.numbers),len(other.numbers))
        left=self.numbers+(0,)*(count-len(self.numbers));right=other.numbers+(0,)*(count-len(other.numbers))
        if left!=right:return -1 if left<right else 1
        if self.pre==other.pre:return 0
        if self.pre is None:return 1
        if other.pre is None:return -1
        for a,b in zip(self.pre,other.pre):
            if a==b:continue
            if a=='':return -1
            if b=='':return 1
            if a.isdigit() and b.isdigit():return -1 if int(a)<int(b) else 1
            if a.isdigit()!=b.isdigit():return -1 if a.isdigit() else 1
            return -1 if a<b else 1
        return -1 if len(self.pre)<len(other.pre) else 1

    def __eq__(self,other):return isinstance(other,Version) and self.compare(other)==0
    def __lt__(self,other):return self.compare(other)<0


def atom_matches(version,atom):
    if atom=='*':return True
    if any(x in atom for x in '[](),|'):return None
    parsed=re.fullmatch(r'(>=|<=|>|<|=|\^|~)?([^\s]+)',atom)
    if not parsed:return None
    operator,bound=parsed.groups();operator=operator or '='
    wildcard=re.fullmatch(r'(\d+(?:\.\d+)*)\.(?:x|X|\*)(?:\.(?:x|X|\*))*',bound)
    if wildcard:
        if operator!='=':return None
        try:actual=Version(version)
        except ValueError:return False
        prefix=tuple(int(x) for x in wildcard[1].split('.'))
        return (actual.numbers+(0,)*len(prefix))[:len(prefix)]==prefix
    try:actual=Version(version);wanted=Version(bound)
    except ValueError:return version==bound if operator in ['=','>=','<=','~','^'] else None
    if operator=='=':return actual==wanted
    if operator=='>':return actual>wanted
    if operator=='>=':return actual>=wanted
    if operator=='<':return actual<wanted
    if operator=='<=':return actual<=wanted
    upper=list(wanted.numbers)
    index=0 if operator=='^' or len(upper)==1 else 1
    upper=upper[:index+1];upper[index]+=1
    maximum=Version('.'.join(str(x) for x in upper)+'-')
    return actual>=wanted and actual<maximum


def matches(version,predicate):
    if not isinstance(version,str) or len(version)>256:return None
    if isinstance(predicate,list):
        if not predicate or len(predicate)>100:return None
        answers=[matches(version,x) for x in predicate]
        return True if True in answers else None if None in answers else False
    if not isinstance(predicate,str) or not predicate or len(predicate)>1000:return None
    atoms=predicate.split()
    if not atoms or len(atoms)>30:return None
    answers=[atom_matches(version,x) for x in atoms]
    return False if False in answers else None if None in answers else True

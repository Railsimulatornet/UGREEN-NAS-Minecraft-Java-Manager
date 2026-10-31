"""Bounded Maven ranges for Forge/NeoForge; unknown comparisons never approve a mod.

Numeric releases and standard prerelease qualifiers are supported. The native loader
remains authoritative, particularly for arbitrary publisher-specific version strings.
"""
import re


def compare(left,right):
    def parse(value):
        match=re.fullmatch(r'(\d+(?:\.\d+)*)([-+A-Za-z][A-Za-z0-9.+\-]*)?',value)
        if not match:return None
        suffix=re.fullmatch(r'(?:-([A-Za-z]+)(?:[.-]?(\d+))?)?',match[2] or '')
        numbers=tuple(int(x) for x in match[1].split('.'))
        if not suffix:return numbers,None
        aliases={'a':'alpha','b':'beta','m':'milestone','cr':'rc','ga':'','final':'','release':''}
        qualifier=aliases.get((suffix[1] or '').lower(),(suffix[1] or '').lower())
        ranks={'alpha':0,'beta':1,'milestone':2,'rc':3,'snapshot':4,'':5,'sp':6}
        if qualifier not in ranks:return numbers,None
        return numbers,(ranks[qualifier],int(suffix[2] or 0))
    a,b=parse(left),parse(right)
    if a is None or b is None:return 0 if left==right else None
    count=max(len(a[0]),len(b[0]))
    a=(a[0]+(0,)*(count-len(a[0])),a[1]);b=(b[0]+(0,)*(count-len(b[0])),b[1])
    if a[0]!=b[0]:return (a[0]>b[0])-(a[0]<b[0])
    if left==right:return 0
    # Publisher families such as 6.0.11-adapted-1.31 have a numeric
    # revision after an identical qualifier. Maven compares those numeric
    # components numerically. Do not guess ordering between different
    # custom qualifiers or between a custom qualifier and a plain release.
    if a[1] is None and b[1] is None:
        family=r'\d+(?:\.\d+)*-([A-Za-z]+(?:-[A-Za-z]+)*)-([0-9]+(?:\.[0-9]+)*)'
        x,y=re.fullmatch(family,left),re.fullmatch(family,right)
        if x and y and x[1].lower()==y[1].lower():
            l=tuple(int(n) for n in x[2].split('.'));r=tuple(int(n) for n in y[2].split('.'))
            count=max(len(l),len(r));l+=(0,)*(count-len(l));r+=(0,)*(count-len(r))
            return (l>r)-(l<r)
    if a[1] is None or b[1] is None:return None
    return (a>b)-(a<b)


def matches(version,predicate):
    if not isinstance(version,str) or not 1<=len(version)<=256:return None
    if not isinstance(predicate,str) or len(predicate)>1000:return None
    predicate=predicate.strip()
    if not predicate:return True
    if re.search(r'[0-9A-Za-z_.+\-]\s+[0-9A-Za-z_.+\-]',predicate):return None
    predicate=re.sub(r'\s+','',predicate)
    # A bare Maven version is a recommendation, not a hard constraint.
    if predicate[0] not in '[(':
        return True if re.fullmatch(r'[0-9A-Za-z_.+\-]{1,256}',predicate) else None
    groups=re.findall(r'[\[(][^\[\]()]*[\])]',predicate)
    if not groups or len(groups)>30 or ','.join(groups)!=predicate.replace(' ',''):return None
    answers=[]
    for group in groups:
        body=group[1:-1]
        if ',' not in body:
            if group[0]!='[' or group[-1]!=']' or not body:return None
            answer=compare(version,body)
            answers.append(None if answer is None else answer==0)
            continue
        if body.count(',')!=1:return None
        lower,upper=body.split(',')
        if not lower and not upper:return None
        if lower and upper:
            order=compare(lower,upper)
            if order is None or order>0 or (order==0 and (group[0]!='[' or group[-1]!=']')):return None
        checks=[]
        if lower:
            order=compare(version,lower)
            checks.append(None if order is None else order>=0 if group[0]=='[' else order>0)
        if upper:
            order=compare(version,upper)
            checks.append(None if order is None else order<=0 if group[-1]==']' else order<0)
        answers.append(False if False in checks else None if None in checks else True)
    return True if True in answers else None if None in answers else False

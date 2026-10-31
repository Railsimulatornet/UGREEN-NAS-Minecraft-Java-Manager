"""Keep a satisfying installed dependency when resolving an official project."""
import json
import pytest
from mcj import mods, sources
from test_security import environment, jar


def artifact(identifier, version, loader, requirement=None):
    if loader=='FABRIC':
        value={'id':identifier,'version':version}
        if requirement is not None:value['depends']={'dependency_fixture':requirement}
        return jar({'fabric.mod.json':json.dumps(value)})
    value='modLoader="javafml"\nloaderVersion="[1,)"\nlicense="MIT"\n[[mods]]\nmodId="'+identifier+'"\nversion="'+version+'"\n'
    if requirement is not None:
        value+='[[dependencies.'+identifier+']]\nmodId="dependency_fixture"\ntype="required"\nversionRange="'+requirement+'"\nside="BOTH"\n'
    return jar({'META-INF/neoforge.mods.toml':value})


@pytest.mark.parametrize('loader,installed,requirement,reuse',[
    ('NEOFORGE','1.5.19','[1.5.15,)',True),
    ('NEOFORGE','1.5.19','[1.5.19]',True),
    ('NEOFORGE','1.5.14','[1.5.15,)',False),
    ('NEOFORGE','1.5.20','[1.5.15,1.5.20)',False),
    ('NEOFORGE','1.5.19','[invalid,)',False),
    ('NEOFORGE',None,'[1.5.15,)',False),
    ('FABRIC','1.5.19','>=1.5.15',True),
    ('FABRIC','1.5.14','>=1.5.15',False),
])
def test_provider_resolution_uses_the_parent_loaders_version_rules(environment,monkeypatch,loader,installed,requirement,reuse):
    app,_,_,_=environment;st=app.state.store;root=st.state.parent
    st.set('server',{**st.get('server'),'version':'26.3','loader':loader,'loader_version':'26.3.0.99' if loader=='NEOFORGE' else '0.18.0'})
    existing=None
    if installed is not None:
        raw=artifact('dependency_fixture',installed,loader)
        existing=mods.stage(st,root,raw,'installed-dependency.jar','upload')
        with st.db() as db:
            db.execute("UPDATE mods SET state='installed',installed_enabled=1,enabled=1 WHERE id=?",(existing['id'],))
            before=dict(db.execute('SELECT * FROM mods WHERE id=?',(existing['id'],)).fetchone())
    parent={'id':10,'links':{'websiteUrl':'https://www.curseforge.com/minecraft/mc-mods/parent-fixture'}}
    child={'id':20,'links':{'websiteUrl':'https://www.curseforge.com/minecraft/mc-mods/dependency-fixture'}}
    raw_files={10:artifact('parent_fixture','1.0',loader,requirement),20:artifact('dependency_fixture','1.5.22',loader)}
    class Provider:
        def file(self,project,source,server):
            return {'id':project['id']+100,'fileName':str(project['id'])+'.jar','releaseType':1,
                    'dependencies':[{'modId':20,'relationType':3}] if project['id']==10 else [],'fixture':project['id']}
        def get(self,path):
            assert path=='/mods/20';return child
    monkeypatch.setattr(sources,'download_curseforge',lambda file:raw_files[file['fixture']])
    prepared=sources.prepare_curseforge(st,root,Provider(),[(parent,sources.reference(parent['links']['websiteUrl']))])
    ids=[item['metadata']['mods'][0]['id'] for item in prepared]
    assert ids==(['parent_fixture'] if reuse else ['parent_fixture','dependency_fixture'])
    if existing:
        with st.db() as db:assert dict(db.execute('SELECT * FROM mods WHERE id=?',(existing['id'],)).fetchone())==before
        assert (root/'staging'/(existing['id']+'.jar')).read_bytes()==raw

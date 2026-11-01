"""Explicit stable-version discovery and metadata preflight. Never changes a live runtime."""
import hashlib
import json
import re
import secrets
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import httpx
from .mods import dependency_report
from .server_settings import normalize
from . import mods,loader_catalogs
from .http_identity import AGENT

MANIFEST='https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
FABRIC='https://meta.fabricmc.net/v2/versions/loader/'
NEOFORGE='https://maven.neoforged.net/releases/net/neoforged/neoforge/'
JAVA_CHANNELS={17:'java17',21:'java21',25:'java25'}


class CatalogTreeBuilder(ET.TreeBuilder):
    def doctype(self,name,pubid,system):
        # Expat reports this after decoding, including UTF-16 declarations.
        # A version catalogue needs neither a DTD nor custom entities.
        raise ValueError('version_metadata_limit')


def neoforge_versions(client,minecraft):
    if minecraft=='1.20.1':return loader_catalogs.available(client,'NEOFORGE',minecraft)
    raw=bytearray()
    with client.stream('GET',NEOFORGE+'maven-metadata.xml') as response:
        response.raise_for_status()
        for block in response.iter_bytes(65536):
            raw.extend(block)
            if len(raw)>2*1024*1024:raise ValueError('version_metadata_limit')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('version_metadata_limit')
    try:document=ET.fromstring(raw,parser=ET.XMLParser(target=CatalogTreeBuilder()))
    except ET.ParseError:raise ValueError('loader_metadata_identity_invalid') from None
    if document.findtext('groupId')!='net.neoforged' or document.findtext('artifactId')!='neoforge':raise ValueError('loader_metadata_identity_invalid')
    parts=minecraft.split('.')
    prefix=(minecraft if parts[0]!='1' else '.'.join(parts[1:]) if len(parts)==3 else parts[1]+'.0')+'.'
    versions={x.text for x in document.findall('./versioning/versions/version') if x.text and x.text.startswith(prefix) and re.fullmatch(r'\d+(?:\.\d+){2,4}',x.text)}
    return sorted(versions,key=lambda value:tuple(int(x) for x in value.split('.')),reverse=True)


def neoforge_catalog(store,minecraft):
    if not re.fullmatch(r'\d+(?:\.\d+){1,2}',minecraft):raise ValueError('invalid_minecraft_version')
    catalog=store.get('version_catalog') or {}
    known={x['id'] for x in catalog.get('releases',[])}|{store.get('server')['version']}
    if minecraft not in known:raise ValueError('stable_version_unverified')
    saved=store.get('neoforge_catalogs') or {};cached=saved.get(minecraft)
    if cached and time.time()-cached['checked']<900:return cached
    with httpx.Client(timeout=20,follow_redirects=False) as client:available=neoforge_versions(client,minecraft)
    source=loader_catalogs.identity('NEOFORGE',minecraft) if minecraft=='1.20.1' else NEOFORGE+'maven-metadata.xml'
    value={'minecraft':minecraft,'versions':available,'checked':time.time(),'source':source}
    saved[minecraft]=value;store.set('neoforge_catalogs',saved)
    return value


def ensure_neoforge_components(store,loader_version,client=None):
    if not re.fullmatch(r'\d+(?:\.\d+){2,4}',loader_version):raise ValueError('stable_loader_unverified')
    key='NEOFORGE:'+loader_version;catalog=store.get('loader_components') or {};cached=catalog.get(key)
    path=store.state/'loader-cache'/('neoforge-'+loader_version+'.jar')
    if cached and path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==cached['sha256']:return cached
    source=NEOFORGE+loader_version+'/neoforge-'+loader_version+'-universal.jar'
    def fetch(provider):
        raw=bytearray()
        with provider.stream('GET',source) as response:
            response.raise_for_status()
            for block in response.iter_bytes(65536):
                raw.extend(block)
                if len(raw)>mods.MAX_JAR:raise ValueError('loader_metadata_limit')
        return bytes(raw)
    if client is not None:raw=fetch(client)
    else:
        with httpx.Client(timeout=25,follow_redirects=False) as provider:raw=fetch(provider)
    metadata=mods.inspect_jar(raw)
    if len(metadata['mods'])!=1 or metadata['mods'][0]['id']!='neoforge' or metadata['mods'][0]['version']!=loader_version:raise ValueError('loader_metadata_identity_invalid')
    result={'loader_version':loader_version,'loader':'NEOFORGE','source':source,'sha256':hashlib.sha256(raw).hexdigest(),
        'components':{'neoforge':loader_version},'checked':time.time(),'integrity':'official_https_artifact; actual runtime loader hash must match'}
    store.atomic(path,raw,0o440);catalog[key]=result;store.set('loader_components',catalog)
    return result

def ensure_loader_components(store,loader_version,client=None):
    if not re.fullmatch(r'\d+\.\d+\.\d+',loader_version):raise ValueError('stable_loader_unverified')
    catalog=store.get('loader_components') or {}
    cached=catalog.get(loader_version)
    path=store.state/'loader-cache'/(loader_version+'.jar')
    if cached and path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==cached['sha256']:
        return cached
    source='https://maven.fabricmc.net/net/fabricmc/fabric-loader/'+loader_version+'/fabric-loader-'+loader_version+'.jar'
    def fetch(provider):
        raw=bytearray()
        with provider.stream('GET',source) as response:
            response.raise_for_status()
            for block in response.iter_bytes(65536):
                raw.extend(block)
                if len(raw)>16*1024*1024:raise ValueError('loader_metadata_limit')
        return bytes(raw)
    if client is not None:raw=fetch(client)
    else:
        with httpx.Client(timeout=25,follow_redirects=False) as provider:raw=fetch(provider)
    metadata=mods.inspect_jar(raw)
    if metadata['mods'][0]['id']!='fabricloader' or metadata['mods'][0]['version']!=loader_version:raise ValueError('loader_metadata_identity_invalid')
    components={}
    def collect(meta):
        for mod in meta['mods']:components[mod['id']]=mod['version']
        for alias in meta.get('provides',[]):components[alias]=meta['mods'][0]['version']
        for child in meta.get('embedded',[]):collect(child)
    collect(metadata)
    result={'loader_version':loader_version,'source':source,'sha256':hashlib.sha256(raw).hexdigest(),
            'components':components,'checked':time.time(),'integrity':'official_https_artifact; actual runtime loader hash must match'}
    store.atomic(path,raw,0o440);catalog[loader_version]=result;store.set('loader_components',catalog)
    return result

def runtime_components(store,configuration):
    result=dict(configuration)
    result.pop('loader_components',None)
    if result.get('loader')=='FABRIC':
        record=(store.get('loader_components') or {}).get(result.get('loader_version'))
        if record:result['loader_components']=record
    elif result.get('loader')=='NEOFORGE':
        key=('NEOFORGE:1.20.1:' if loader_catalogs.legacy_neoforge(result) else 'NEOFORGE:')+str(result.get('loader_version'))
        record=(store.get('loader_components') or {}).get(key)
        if record:result['loader_components']=record
    elif result.get('loader')=='FORGE':
        key=loader_catalogs.identity('FORGE',result['version'],result['loader_version'])['key']
        record=(store.get('loader_components') or {}).get(key)
        if record:result['loader_components']=record
    return result

def ensure_runtime_components(store,configuration):
    # A fresh NeoForge installation has not necessarily opened version planning.
    # Acquire the same official proof before maintenance; never trust a runtime
    # file merely because its version string matches.
    if configuration.get('loader')=='FORGE' or loader_catalogs.legacy_neoforge(configuration):
        loader_catalogs.ensure_components(store,configuration['loader'],configuration['version'],configuration['loader_version'])
    elif configuration.get('loader')=='NEOFORGE':ensure_neoforge_components(store,configuration['loader_version'])
    elif configuration.get('loader')=='FABRIC':ensure_loader_components(store,configuration['loader_version'])
    return runtime_components(store,configuration)

def read_json(client,url,sha1=None):
    response=client.get(url);response.raise_for_status()
    if len(response.content)>2*1024*1024:raise ValueError('version_metadata_limit')
    if sha1 and hashlib.sha1(response.content).hexdigest()!=sha1:raise ValueError('version_metadata_hash_mismatch')
    return response.json()

def metadata_url(value):
    url=urlparse(value)
    if url.scheme!='https' or url.netloc!='piston-meta.mojang.com' or not re.fullmatch(r'/v1/packages/[0-9a-f]{40}/[A-Za-z0-9._-]+\.json',url.path):
        raise ValueError('version_metadata_source_invalid')
    return value

def refresh(store):
    with httpx.Client(timeout=20,follow_redirects=False,headers={'User-Agent':AGENT}) as client:
        manifest=read_json(client,MANIFEST)
    releases=[{'id':x['id'],'released':x['releaseTime'],'url':metadata_url(x['url']),'sha1':x['sha1']}
              for x in manifest['versions'] if x['type']=='release' and re.fullmatch(r'\d+(?:\.\d+){1,2}',x['id'])]
    latest=manifest['latest']['release']
    if latest not in {x['id'] for x in releases}:raise ValueError('latest_stable_version_unverified')
    catalog={'checked':time.time(),'latest_stable':latest,'releases':releases,'source':MANIFEST,'automatic_minecraft_upgrades':False}
    store.set('version_catalog',catalog)
    store.event('server','stable_versions_checked',data={'latest_stable':latest,'count':len(releases)})
    return catalog

def check(store,configuration,records=None):
    configuration=normalize(store.get('server'),configuration)
    version=configuration.get('version','');loader=configuration.get('loader','');java=configuration.get('java')
    if not isinstance(version,str) or not re.fullmatch(r'\d+(?:\.\d+){1,2}',version):raise ValueError('explicit_stable_version_required')
    if java not in JAVA_CHANNELS:raise ValueError('unsupported_java_channel')
    if loader not in {'FABRIC','FORGE','NEOFORGE'}:raise ValueError('invalid_modloader')
    catalog=store.get('version_catalog') or refresh(store)
    release=next((x for x in catalog['releases'] if x['id']==version),None)
    if not release:raise ValueError('stable_version_not_in_catalog')
    with httpx.Client(timeout=20,follow_redirects=False) as client:
        details=read_json(client,metadata_url(release['url']),release['sha1'])
        loaders=read_json(client,FABRIC+version) if loader=='FABRIC' else []
        neo_loaders=neoforge_versions(client,version) if loader=='NEOFORGE' else []
        forge_loaders=loader_catalogs.available(client,'FORGE',version) if loader=='FORGE' else []
    if details['id']!=version or details['type']!='release':raise ValueError('explicit_stable_version_required')
    required_java=details.get('javaVersion',{}).get('majorVersion')
    issues=[]
    current=store.get('server')
    if version!=current['version'] and configuration['world']==current.get('world','world'):
        issues.append({'issue':'version_change_requires_separate_world'})
    if not isinstance(required_java,int):issues.append({'issue':'required_java_unverified'})
    elif java<required_java:issues.append({'issue':'java_too_old','required':required_java,'selected':java})
    trusted=store.get('guard_catalog') or {'artifacts':[]}
    guard=next((x for x in trusted['artifacts'] if x['minecraft']==version and x['loader']==loader),None)
    stable_loaders=neo_loaders if loader=='NEOFORGE' else forge_loaders if loader=='FORGE' else [x['loader']['version'] for x in loaders if x.get('loader',{}).get('stable')]
    loader_version=configuration.get('loader_version')
    if not loader_version and stable_loaders:
        verified=[x for x in (guard or {}).get('tested_loaders',[]) if x in stable_loaders]
        loader_version=verified[0] if verified else stable_loaders[0]
    selected={**configuration,'loader_version':loader_version,'java':java}
    if loader=='FABRIC' and loader_version in stable_loaders:
        selected['loader_components']=ensure_loader_components(store,loader_version)
    elif (loader=='FORGE' or loader_catalogs.legacy_neoforge(selected)) and loader_version in stable_loaders:
        selected['loader_components']=loader_catalogs.ensure_components(store,loader,version,loader_version)
    elif loader=='NEOFORGE' and loader_version in stable_loaders:
        selected['loader_components']=ensure_neoforge_components(store,loader_version)
    if loader_version not in stable_loaders:issues.append({'issue':'stable_loader_unverified'})
    if not guard:issues.append({'issue':'visitor_guard_adapter_missing'})
    elif 'tested_loaders' in guard and (guard.get('runtime_test')!='passed' or loader_version not in guard['tested_loaders'] or java!=guard.get('java',25)):
        issues.append({'issue':'guard_runtime_combination_not_tested'})
    if guard:
        from .player_admission import require_target
        try:require_target(selected['properties'],guard,selected)
        except ValueError as exc:issues.append({'issue':str(exc)})
    if records is None:
        from .mods import proposed_records
        with store.db() as db:records=proposed_records([dict(x) for x in db.execute("SELECT * FROM mods WHERE state!='superseded'")])
        records=[x for x in records if x['enabled']]
    if guard:
        artifacts=[guard,*guard.get('dependencies',[])]
        protected={x['sha256'] for x in artifacts}
        # The controller replaces old system guard files, retaining every user mod.
        records=[x for x in records if x.get('source')!='system' or x.get('sha256') in protected]
        present={x.get('sha256') for x in records}
        for artifact in artifacts:
            if artifact.get('metadata') and artifact['sha256'] not in present:
                records.append({'id':artifact['sha256'],'sha256':artifact['sha256'],'source':'system','metadata':artifact['metadata']})
    dependencies=dependency_report(records,selected)
    issues.extend(dependencies['issues'])
    return {'configuration':selected,'required_java':required_java,'stable_loaders':stable_loaders,
            'image_channel':'itzg/minecraft-server:'+JAVA_CHANNELS[java],'guard':guard,
            'metadata_checks':'passed' if not issues else 'blocked','issues':issues,
            'dependencies':dependencies,'runtime_test':'not_tested','visitor_client_test':'not_verified',
            'approval_required':True,'backup_required':True,'automatic_minecraft_upgrades':False,
            'checked':time.time(),'source':release['url']}

def create_plan(store,configuration,actor):
    from .mods import fingerprint
    with store.change_lock():
        report=check(store,configuration);identifier=secrets.token_hex(16)
        current=store.get('server');snapshot=fingerprint(store)
        with store.db() as db:db.execute('INSERT INTO version_plans(id,created,actor,configuration,report,state,based_on,mod_fingerprint) VALUES(?,?,?,?,?,?,?,?)',
            (identifier,time.time(),actor,json.dumps(report['configuration']),json.dumps(report),
             'metadata_passed' if report['metadata_checks']=='passed' else 'blocked',json.dumps(current,sort_keys=True),snapshot))
    store.event('maintenance','version_plan_created',actor,{'id':identifier,'version':configuration['version'],'metadata_checks':report['metadata_checks']})
    return {'id':identifier,**report}

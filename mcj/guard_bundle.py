"""Read the image's protection artifacts; never infer a client acceptance verdict."""
import hashlib
import json
from pathlib import Path
import re
from .guard_artifacts import artifact_identity
from .project_paths import project_path
from .store import Store

DIRECTORY=Path(__file__).resolve().parents[1]/'artifacts'
JAVA={('26.3','NEOFORGE'):25,('1.21.1','NEOFORGE'):21}


def read(directory=None):
    directory=Path(directory or DIRECTORY)
    index=directory/'catalog.json'
    if index.is_symlink():raise RuntimeError('unsafe_guard_artifact')
    names=json.loads(index.read_text())['manifests'] if index.exists() else ['guard.json']
    if not isinstance(names,list) or not 1<=len(names)<=2 or len(set(names))!=len(names):raise RuntimeError('unsafe_guard_artifact')
    entries=[];identities=set()
    for name in names:
        if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.json',name):raise RuntimeError('unsafe_guard_artifact')
        manifest=directory/name
        if manifest.is_symlink() or manifest.stat().st_size>65536:raise RuntimeError('unsafe_guard_artifact')
        entry=json.loads(manifest.read_text());filename,checksum=artifact_identity(entry)
        identity=(entry.get('minecraft'),entry.get('loader'))
        if identity not in JAVA or identity in identities or entry.get('java',JAVA[identity])!=JAVA[identity] or entry.get('dependencies'):
            raise RuntimeError('unsafe_guard_artifact')
        artifact=directory/filename
        if artifact.is_symlink() or artifact.stat().st_size>64*1024**2:raise RuntimeError('unsafe_guard_artifact')
        raw=artifact.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=checksum:raise RuntimeError('guard_artifact_integrity_failed')
        entry={**entry,'java':JAVA[identity],'path':'releases/guards/neoforge-'+entry['minecraft']+'/'+filename}
        entries.append(entry);identities.add(identity)
    return {'artifacts':entries}


def install_registry(root,directory=None):
    """Add verified candidates, retaining old identities for backup verification.

    This does not replace the live guard, roles, game data or acceptance records.
    A live replacement still follows the backup and isolated-test maintenance path.
    """
    directory=Path(directory or DIRECTORY)
    registry=project_path(root,'releases/guards/registry.json')
    if registry.is_symlink():raise RuntimeError('unsafe_guard_registry')
    if not registry.exists():return False
    if registry.stat().st_size>1024*1024:raise RuntimeError('unsafe_guard_registry')
    bundled=read(directory);previous=json.loads(registry.read_text())
    boundary=registry.parent.resolve()
    if boundary!=registry.parent.absolute():raise RuntimeError('unsafe_guard_registry')
    for entry in bundled['artifacts']:
        destination=project_path(root,entry['path'])
        if destination.is_symlink() or not destination.resolve().is_relative_to(boundary):raise RuntimeError('unsafe_guard_artifact')
        raw=(directory/entry['filename']).read_bytes()
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('guard_artifact_integrity_failed')
        else:Store.atomic(destination,raw,0o440)
    current={x['sha256'] for x in bundled['artifacts']}
    retained={}
    for entry in [*previous.get('retained_artifacts',[]),*previous.get('artifacts',[])]:
        artifact_identity(entry)
        if entry['sha256'] not in current:retained[entry['sha256']]=entry
    value={**bundled,'retained_artifacts':list(retained.values())}
    if value!=previous:Store.atomic(registry,json.dumps(value).encode(),0o640)
    return True

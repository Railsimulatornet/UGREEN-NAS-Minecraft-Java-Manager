"""Restore known backup identities without executing an older protection artifact."""
import hashlib
from pathlib import Path
import re
from .project_paths import project_path
from .store import Store


def artifact_identity(entry):
    name=entry.get('filename');checksum=entry.get('sha256')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,160}\.jar',name):raise RuntimeError('unsafe_guard_artifact')
    if not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}',checksum):raise RuntimeError('unsafe_guard_artifact')
    return name,checksum


def restore_current_guard(root,data,archived,active,retained):
    identity=artifact_identity(archived)
    known=[x for x in [active,*retained] if (x.get('minecraft'),x.get('loader'))==(active['minecraft'],active['loader'])
           and (x.get('filename'),x.get('sha256'))==identity]
    if not known:raise RuntimeError('backup_guard_not_trusted')
    previous=known[0];old_paths=[]
    for artifact in [previous,*previous.get('dependencies',[])]:
        name,checksum=artifact_identity(artifact);path=Path(data)/'mods'/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>64*1024*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:
            raise RuntimeError('backup_guard_integrity_failed')
        old_paths.append(path)
    prepared=[];boundary=project_path(root,'releases/guards').resolve()
    for artifact in [active,*active.get('dependencies',[])]:
        name,checksum=artifact_identity(artifact);source=project_path(root,artifact['path'])
        if source.is_symlink() or not source.resolve().is_relative_to(boundary) or not source.is_file() or source.stat().st_size>64*1024*1024:raise RuntimeError('unsafe_guard_artifact')
        raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=checksum:raise RuntimeError('guard_artifact_integrity_failed')
        destination=Path(data)/'mods'/name
        if destination.exists() and destination not in old_paths:
            if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest()!=checksum:raise RuntimeError('backup_guard_filename_conflict')
        prepared.append((destination,raw))
    # Identity and all new bytes are checked before changing this disposable copy.
    for path in old_paths:path.unlink()
    for destination,raw in prepared:Store.atomic(destination,raw,0o440)
    return active

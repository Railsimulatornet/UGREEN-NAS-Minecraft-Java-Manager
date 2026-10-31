"""Conservative, read-only capacity estimates for the existing backup/test pipeline."""
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import time
from .project_paths import project_path

GIB=1024**3
RESERVE=20*GIB
PREPARATION=2*GIB
LIMIT=300000
KINDS={'backup','apply_mods','server_settings','version_test','version_apply','restore','restore_test','world_change','world_delete','world_export','curseforge_install'}


def tree_size(folder):
    """Count allocated copy bytes, without following links or special files."""
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir():raise ValueError('storage_inventory_unavailable')
    logical=allocated=count=0;pending=[folder]
    while pending:
        parent=pending.pop()
        with os.scandir(parent) as entries:
            for entry in entries:
                if parent==folder and entry.name in {'logs','crash-reports'}:continue
                # Windows DirEntry caches omit link counts; request full metadata.
                info=os.stat(entry.path,follow_symlinks=False);count+=1
                if count>LIMIT:raise ValueError('storage_inventory_limit')
                if stat.S_ISDIR(info.st_mode):pending.append(Path(entry.path));allocated+=4096
                elif stat.S_ISREG(info.st_mode) and info.st_nlink==1:
                    logical+=info.st_size;allocated+=math.ceil(info.st_size/4096)*4096
                else:raise ValueError('storage_inventory_unsafe')
    return {'bytes':logical,'copy_bytes':allocated,'entries':count}


def archive_size(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1:raise ValueError('storage_archive_unavailable')
    logical=allocated=count=0
    with tarfile.open(path,'r:gz') as stream:
        for member in stream:
            count+=1
            name=PurePosixPath(member.name)
            if count>LIMIT:raise ValueError('storage_inventory_limit')
            if not name.parts or name.is_absolute() or '..' in name.parts or '\\' in member.name or ':' in member.name or not (member.isdir() or member.isfile()):raise ValueError('storage_archive_unsafe')
            if name.parts[0]!='server' and member.name not in {'runtime.json','guard.json','mod-manifest.json','pack-state.json'}:raise ValueError('storage_archive_unsafe')
            logical+=member.size;allocated+=4096 if member.isdir() else math.ceil(member.size/4096)*4096
    return {'bytes':logical,'copy_bytes':allocated,'entries':count}


def existing_parent(path):
    path=Path(path)
    while not path.exists():
        if path.is_symlink() or path.parent==path:raise ValueError('storage_inventory_unavailable')
        path=path.parent
    if path.is_symlink() or not path.is_dir():raise ValueError('storage_inventory_unsafe')
    return path


def forecast(root,backups,kind,archive=None):
    if kind not in KINDS:raise ValueError('invalid_storage_operation')
    current=tree_size(project_path(root,'server'))
    # PAX headers, tiny files and incompressible content all consume real space.
    backup_bytes=math.ceil((current['bytes']+current['entries']*8192+10*1024**2)*1.05)
    copy_bytes=current['copy_bytes']
    if kind in {'restore','restore_test'}:
        if archive is None:raise ValueError('storage_archive_unavailable')
        copy_bytes=max(copy_bytes,archive_size(archive)['copy_bytes'])
    roles=[]
    if kind!='restore_test':roles.append(('backup',Path(backups),backup_bytes))
    if kind not in {'backup','world_delete'}:
        # Existing staged imports/mods may be copied into the candidate too.
        staging=project_path(root,'staging')
        staged=tree_size(staging)['copy_bytes'] if staging.exists() else 0
        work=copy_bytes+staged+PREPARATION
        if kind=='world_export':work+=backup_bytes
        roles.append(('temporary',project_path(root,'.restore-tests'),work))
    volumes={}
    for role,path,required in roles:
        parent=existing_parent(path);device=parent.stat().st_dev
        capacity=shutil.disk_usage(parent)
        value=volumes.setdefault(device,{'roles':[],'required_bytes':0,'free_bytes':capacity.free,'reserve_bytes':RESERVE})
        value['roles'].append(role);value['required_bytes']+=required;value['free_bytes']=min(value['free_bytes'],capacity.free)
    for value in volumes.values():
        value['remaining_bytes']=value['free_bytes']-value['required_bytes']
        value['sufficient']=value['remaining_bytes']>=value['reserve_bytes']
    return {'checked_at':time.time(),'kind':kind,'sufficient':all(v['sufficient'] for v in volumes.values()),'volumes':list(volumes.values()),'estimate':True,'preparation_buffer_bytes':PREPARATION if any(r[0]=='temporary' for r in roles) else 0}


def require(root,backups,kind,archive=None):
    value=forecast(root,backups,kind,archive)
    if not value['sufficient']:raise ValueError('insufficient_operation_space')
    return value

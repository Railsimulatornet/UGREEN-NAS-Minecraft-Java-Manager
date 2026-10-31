"""World mutations use the existing backed-up promotion path; exports are snapshots."""
import hashlib
import json
from pathlib import Path
import secrets
import re
import shutil
import time
import zipfile
from . import maintenance, worlds, storage_preflight
from .project_paths import project_path
from .store import Store


def change(c, configuration, actor):
    return maintenance.apply_change(c, 'world', actor, configuration=configuration)


def existing(c, name):
    name = worlds.valid_name(name)
    path = project_path(c.ROOT, 'server')/name
    if path.is_symlink() or not path.is_dir() or path.resolve().parent != project_path(c.ROOT,'server').resolve():
        raise ValueError('world_unavailable')
    worlds.validate_level(path/'level.dat')
    return path


def export(c, name, actor):
    name = worlds.valid_name(name);existing(c,name)
    storage_preflight.require(c.ROOT,c.BACKUPS,'world_export')
    st = maintenance.store(c)
    container, running = maintenance.idle_gate(c)
    scratch = None
    try:
        backup = maintenance.full_backup(c, 'pre_world_export', actor, resume=True)
        scratch, data, _, _ = c.extract_archive(backup['path'])
        folder = data/name
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError('world_unavailable')
        identifier = secrets.token_hex(16)
        destination = st.state/'world-exports';destination.mkdir(mode=0o750,exist_ok=True)
        target = destination/(identifier+'.zip')
        size = 0;count = 0
        try:
            with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as output:
                for path in sorted(folder.rglob('*')):
                    if path.is_symlink():raise ValueError('unsafe_world_directory')
                    if not path.is_file() or path.name=='session.lock':continue
                    count+=1;size+=path.stat().st_size
                    if count>worlds.MAX_FILES or size>worlds.MAX_EXPANDED:raise ValueError('world_export_limit')
                    output.write(path,str(Path(name)/path.relative_to(folder)).replace('\\','/'))
        except Exception:
            target.unlink(missing_ok=True);raise
        result={'id':identifier,'name':name,'created':time.time(),'size':target.stat().st_size,'backup_id':backup['manager_backup_id']}
        Store.atomic(destination/(identifier+'.json'),json.dumps(result).encode(),0o640)
        st.event('server','world_exported',actor,result)
        return result
    finally:
        if scratch and scratch.exists():maintenance.safe_remove(c,scratch)
        c.gate(not running)



def retire_import(st, root, name):
    """A deleted imported world must not reappear as a staged import."""
    records=st.get('world_imports') or []
    removed=[x for x in records if x['name']==name]
    retained=[x for x in records if x['name']!=name]
    base=project_path(root,'staging/worlds');folders=[]
    for identifier in {x['id'] for x in removed}:
        if not re.fullmatch('[0-9a-f]{64}',identifier):raise ValueError('world_staging_integrity_failed')
        if any(x['id']==identifier for x in retained):continue
        folder=base/identifier
        if folder.is_symlink() or not folder.resolve().is_relative_to(Path(root).resolve()):raise ValueError('world_staging_integrity_failed')
        if folder.exists():
            if not folder.is_dir():raise ValueError('world_staging_integrity_failed')
            folders.append(folder)
    if removed:st.set('world_imports',retained)
    for folder in folders:shutil.rmtree(folder)
    return len(removed)


def delete(c, name, actor):
    st=maintenance.store(c);name=worlds.valid_name(name)
    if name==st.get('server').get('world','world'):raise ValueError('active_world_protected')
    folder=existing(c,name)
    storage_preflight.require(c.ROOT,c.BACKUPS,'world_delete')
    container,running=maintenance.idle_gate(c)
    moved=None
    try:
        backup=maintenance.full_backup(c,'pre_world_delete',actor,resume=False)
        if name==st.get('server').get('world','world'):raise ValueError('active_world_protected')
        moved=folder.with_name('.deleted-'+secrets.token_hex(16))
        folder.rename(moved)
        if running:c.guard_integrity();container.start();c.wait_health()
        shutil.rmtree(moved);moved=None
        retired_imports=retire_import(st,c.ROOT,name)
        st.event('server','world_deleted',actor,{'name':name,'backup_id':backup['manager_backup_id'],'retired_imports':retired_imports})
        return {'name':name,'deleted':True,'backup_id':backup['manager_backup_id'],'retired_imports':retired_imports}
    except Exception:
        if moved and moved.exists():moved.rename(folder)
        current=c.target();current.reload()
        if running and current.status!='running':c.guard_integrity();current.start();c.wait_health()
        raise
    finally:c.gate(not running)

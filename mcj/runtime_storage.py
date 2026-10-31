"""Inventory uniquely owned runtime directories; never remove Docker or shared libraries."""
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import stat
import time
from .project_paths import project_path

PREFIXES = {'NeoForge':'libraries/net/neoforged/neoforge', 'Forge':'libraries/net/minecraftforge/forge',
            'Fabric':'libraries/net/fabricmc/fabric-loader', 'Minecraft':'versions'}


def cleanup_policy(value):
    value=value or {}
    if not isinstance(value,dict) or set(value)-{'enabled','retention_days'}:raise ValueError('invalid_setting')
    enabled=value.get('enabled',False);days=value.get('retention_days',14)
    if type(enabled) is not bool or type(days) is not int or not 1<=days<=365:raise ValueError('invalid_runtime_retention')
    return {'enabled':enabled,'retention_days':days}


def independent_rollback_copy(snapshot, current, records, digests):
    """A saved server tree owns its runtime; it does not need the live cache copy."""
    try:
        if not snapshot.is_dir() or any(p.is_symlink() for p in [snapshot,*snapshot.parents]):return False
        for relative,size,_ in records:
            target=snapshot/relative
            if any(p.is_symlink() for p in [target,*target.parents]):return False
            info=target.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size!=size:return False
            if relative not in digests:digests[relative]=hashlib.sha256((current/relative).read_bytes()).digest()
            if hashlib.sha256(target.read_bytes()).digest()!=digests[relative]:return False
        return bool(records)
    except OSError:return False


def inventory(root, current):
    root=Path(root);server=project_path(root,'server')
    rollback=[]
    for path in project_path(root,'.rollback').glob('*/runtime/runtime.json'):
        if path.is_symlink() or path.stat().st_size>65536:raise ValueError('rollback_protection_unverified')
        rollback.append((path.parents[1],json.loads(path.read_text())))
    result=[]
    for kind,prefix in PREFIXES.items():
        parent=server/prefix
        if not parent.is_dir() or parent.is_symlink() or not parent.resolve().is_relative_to(server.resolve()) or any(p.is_symlink() for p in parent.parents if p!=server.parent):continue
        for folder in sorted(parent.iterdir()):
            if not re.fullmatch(r'[0-9][A-Za-z0-9_.+-]{0,70}',folder.name) or folder.is_symlink() or not folder.is_dir():continue
            records=[];unsafe=False
            for path in folder.rglob('*'):
                info=path.lstat()
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) or (stat.S_ISREG(info.st_mode) and info.st_nlink>1):unsafe=True
                if stat.S_ISREG(info.st_mode):records.append((str(path.relative_to(folder)),info.st_size,info.st_mtime_ns))
                if len(records)>10000:unsafe=True;break
            loader={'NeoForge':'NEOFORGE','Forge':'FORGE','Fabric':'FABRIC'}.get(kind)
            def used(runtime):return folder.name==runtime.get('version') if kind=='Minecraft' else loader==runtime.get('loader') and folder.name==runtime.get('loader_version')
            relative=prefix+'/'+folder.name
            active=used(current);references=[snapshot for snapshot,value in rollback if used(value)]
            copies=[];required=[];digests={}
            if not active and not unsafe:
                for snapshot in references:
                    (copies if independent_rollback_copy(snapshot/'server'/relative,folder,records,digests) else required).append(snapshot.name)
            retained=bool(required) or bool(references) and (active or unsafe)
            result.append({'id':hashlib.sha256(relative.encode()).hexdigest()[:32],'kind':kind,'version':folder.name,'path':relative,
                'size':sum(x[1] for x in records),'files':len(records),'status':'active' if active else 'rollback' if retained else 'shared' if unsafe else 'unused',
                'deletable':bool(records) and not (active or retained or unsafe),
                'independent_rollback_copies':len(copies),'required_by_rollbacks':required,
                'last_modified':max([folder.stat().st_mtime]+[x[2]/1_000_000_000 for x in records]),
                'fingerprint':hashlib.sha256(json.dumps(sorted(records)).encode()).hexdigest()})
    return result


def delete(st, root, identifier, actor, confirmation=None, *, automatic=False, now=None):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('runtime_file_unavailable')
    with st.change_lock(),st.db(immediate=True) as db:
        if db.execute("SELECT 1 FROM jobs WHERE state='running'").fetchone():raise ValueError('storage_operation_busy')
        item=next((x for x in inventory(root,st.get('server')) if x['id']==identifier),None)
        if not item:raise ValueError('runtime_file_unavailable')
        if not item['deletable']:raise ValueError('delete_item_protected')
        if automatic:
            cfg=cleanup_policy(st.get('runtime_cleanup'));approval=st.get('runtime_cleanup_approval') or {}
            user=db.execute('SELECT enabled,admin FROM users WHERE id=?',(actor,)).fetchone()
            if not cfg['enabled'] or approval.get('actor')!=actor or not user or not user['enabled'] or not user['admin']:raise ValueError('runtime_cleanup_not_authorized')
            if item['last_modified']>(time.time() if now is None else now)-cfg['retention_days']*86400:raise ValueError('runtime_cleanup_too_recent')
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('planned','queued') AND kind IN ('version_test','version_apply','apply_mods','server_settings','world_change','restore','restore_test')").fetchone():raise ValueError('storage_operation_busy')
        if confirmation is None:return {**item,'confirmation':item['fingerprint'],'bytes':item['size'],'count':1}
        if not secrets.compare_digest(confirmation,item['fingerprint']):raise ValueError('delete_selection_changed')
        server=project_path(root,'server').resolve();folder=server/item['path']
        if folder.resolve().parent!=(server/str(Path(item['path']).parent)).resolve() or server not in folder.resolve().parents:raise ValueError('unsafe_delete_file')
        quarantine=folder.with_name('.delete-'+secrets.token_hex(12));folder.rename(quarantine)
        shutil.rmtree(quarantine)
    st.event('server','runtime_files_deleted',actor,{'kind':item['kind'],'version':item['version'],'bytes':item['size'],'automatic':automatic})
    return {'deleted':True,'bytes':item['size'],'id':identifier}


def cleanup(st,root,now=None):
    """Re-inventory and authorize every deletion; never remove rollback trees or images."""
    now=time.time() if now is None else now
    with st.change_lock():
        cfg=cleanup_policy(st.get('runtime_cleanup'));approval=st.get('runtime_cleanup_approval') or {}
        if not cfg['enabled']:return {'state':'disabled','count':0,'bytes':0}
        actor=approval.get('actor')
        with st.db() as db:
            user=db.execute('SELECT enabled,admin FROM users WHERE id=?',(actor,)).fetchone()
            busy=db.execute("SELECT 1 FROM jobs WHERE state='running' OR (state IN ('planned','queued') AND kind IN ('version_test','version_apply','apply_mods','server_settings','world_change','restore','restore_test'))").fetchone()
        if not user or not user['enabled'] or not user['admin']:return {'state':'approval_unavailable','count':0,'bytes':0}
        if busy:return {'state':'busy','count':0,'bytes':0}
        removed=[];freed=0
        for item in inventory(root,st.get('server')):
            if not item['deletable'] or item['last_modified']>now-cfg['retention_days']*86400:continue
            result=delete(st,root,item['id'],actor,item['fingerprint'],automatic=True,now=now)
            removed.append({'kind':item['kind'],'version':item['version'],'id':item['id']});freed+=result['bytes']
        result={'state':'completed','checked_at':now,'count':len(removed),'bytes':freed,'removed':removed}
        st.set('runtime_cleanup_last',result)
        if removed:st.event('server','runtime_cleanup_completed',actor,{'count':len(removed),'bytes':freed})
        return result

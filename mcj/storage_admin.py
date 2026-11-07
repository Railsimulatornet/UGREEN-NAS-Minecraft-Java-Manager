"""Delete only explicitly inventoried files, keeping recovery and active work safe."""
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import stat
import time
from . import backup_inventory


def identifiers(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 100 or len(set(values)) != len(values) or any(not isinstance(x, str) or not re.fullmatch('[0-9a-f]{32}', x) for x in values):
        raise ValueError('invalid_delete_selection')
    return sorted(values)


def backup_protection(db, root, *, rollback_root=None):
    protected = {x[0] for x in db.execute('SELECT backup_id FROM version_plans WHERE backup_id IS NOT NULL')}
    protected.update(x[0] for x in db.execute('SELECT id FROM backups WHERE restored IS NOT NULL'))
    rows = [dict(x) for x in db.execute("SELECT * FROM backups WHERE state='verified' ORDER BY created DESC")]
    available = [x for x in rows if backup_inventory.archive_info(root, x)['archive_available']]
    if available:
        protected.add(available[0]['id'])
    for row in db.execute("SELECT payload FROM jobs WHERE state IN ('planned','queued','running') AND kind IN ('restore','restore_test')"):
        protected.add(json.loads(row[0]).get('id'))
    if rollback_root:
        for path in Path(rollback_root).glob('*/journal.json'):
            if path.is_symlink() or path.stat().st_size > 65536:
                raise ValueError('rollback_protection_unverified')
            protected.add(json.loads(path.read_text()).get('backup_id'))
    return protected


def delete(st, root, kind, selected, actor, *, confirmation=None, current_fingerprint=None, rollback_root=None):
    selected = identifiers(selected)
    root = Path(root)
    with st.change_lock(), st.db(immediate=True) as db:
        if db.execute("SELECT 1 FROM jobs WHERE state='running' AND kind IN ('backup','restore','restore_test','version_test','version_apply','apply_mods','server_settings','client_pack_build')").fetchone():
            raise ValueError('storage_operation_busy')
        if kind == 'backup':
            protected = backup_protection(db, root, rollback_root=rollback_root)
            table = 'backups'
        elif kind == 'client_pack':
            if current_fingerprint is None:
                raise ValueError('client_pack_current_unverified')
            # Exports are reproducible. Even the current export may be removed
            # after preview; this never removes installed server mods.
            protected = set()
            table = 'client_packs'
        else:
            raise ValueError('invalid_delete_selection')
        rows, files = [], []
        for identifier in selected:
            row = db.execute('SELECT * FROM '+table+' WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise ValueError('delete_item_unavailable')
            row = dict(row)
            if identifier in protected or row.get('state') in ('running', 'interrupted'):
                raise ValueError('delete_item_protected')
            if kind == 'backup':
                backup_inventory.require_available(root, row)
                names = [row['path'], row['path'][:-7]+'.json']
            else:
                names = [identifier+'.mrpack']
            for name in names:
                path = root/name
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or path.resolve().parent != root.resolve():
                    raise ValueError('unsafe_delete_file')
                files.append(path)
            rows.append(row)
        size = sum(path.stat().st_size for path in files)
        live_links = sum(db.execute('SELECT COUNT(*) FROM client_pack_links WHERE pack_id=? AND revoked IS NULL AND (expires=0 OR expires>?)',(row['id'],time.time())).fetchone()[0] for row in rows) if kind=='client_pack' else 0
        current_packs = sum(row['fingerprint']==current_fingerprint for row in rows) if kind=='client_pack' else 0
        versions = [json.loads(row['manifest']).get('version','') for row in rows] if kind=='client_pack' else []
        digest = hashlib.sha256(json.dumps({'kind':kind,'ids':selected,'files':[(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in files],
            'current_fingerprint':current_fingerprint,'active_links':live_links,'current_packs':current_packs},sort_keys=True).encode()).hexdigest()
        result = {'ids':selected,'bytes':size,'confirmation':digest,'active_links':live_links,'count':len(rows),'current_packs':current_packs,'versions':versions}
        if confirmation is None:
            return result
        if not secrets.compare_digest(confirmation,digest):
            raise ValueError('delete_selection_changed')
        quarantine = root/('.delete-'+secrets.token_hex(12))
        quarantine.mkdir(mode=0o700)
        moved=[]
        try:
            for source in files:
                source.rename(quarantine/source.name);moved.append(source)
            for row in rows:
                if kind=='client_pack':
                    # Removing the capability rows makes every associated link unusable.
                    db.execute('DELETE FROM client_pack_links WHERE pack_id=?',(row['id'],))
                db.execute('DELETE FROM '+table+' WHERE id=?',(row['id'],))
            db.commit()
        except Exception:
            db.rollback()
            for source in reversed(moved):
                (quarantine/source.name).rename(source)
            quarantine.rmdir()
            raise
        shutil.rmtree(quarantine)
    st.event('backup' if kind=='backup' else 'mods',kind+'_deleted',actor,{'ids':selected,'bytes':size,'revoked_links':live_links})
    return {**result,'deleted':True}

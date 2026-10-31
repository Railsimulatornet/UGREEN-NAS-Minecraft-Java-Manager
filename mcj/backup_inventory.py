"""Bounded archive reconciliation and keyset paging of every recorded attempt."""
import base64
import json
import math
from pathlib import Path
import re
import stat
import time
from .store import Store

ARCHIVE = re.compile(r'\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gz')


def archive_info(root, row):
    result = {'archive_state': 'not_created', 'archive_available': False,
              'restore_status': row.get('restore_status') or 'not_tested',
              'restore_tested': row.get('restore_tested')}
    name = row.get('path')
    if not name:
        return result
    if not isinstance(name, str) or not ARCHIVE.fullmatch(name):
        return {**result, 'archive_state': 'unsafe'}
    root = Path(root)
    metadata_path = root / (name[:-7] + '.json')
    metadata = None
    try:
        info = metadata_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            return {**result, 'archive_state': 'unsafe'}
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if not isinstance(metadata, dict) or metadata.get('path') != name:
            return {**result, 'archive_state': 'inconsistent'}
    except FileNotFoundError:
        pass
    except (OSError, ValueError, UnicodeError):
        return {**result, 'archive_state': 'unknown'}
    try:
        info = (root / name).lstat()
    except FileNotFoundError:
        return {**result, 'archive_state': 'expired' if metadata and metadata.get('archive_state') == 'expired' else 'missing'}
    except OSError:
        return {**result, 'archive_state': 'unknown'}
    if not stat.S_ISREG(info.st_mode):
        return {**result, 'archive_state': 'unsafe'}
    if metadata is None:
        return {**result, 'archive_state': 'metadata_missing'}
    if (metadata.get('archive_state') == 'expired' or metadata.get('state') != 'verified'
            or not isinstance(row.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',row['sha256'])
            or metadata.get('sha256') != row.get('sha256')
            or metadata.get('size') != row.get('size') or info.st_size != row.get('size')):
        return {**result, 'archive_state': 'inconsistent'}
    # A newer recorded failed test must not be hidden by an older metadata success.
    tested = metadata.get('restore_tested')
    if isinstance(tested, (int, float)) and math.isfinite(tested) and tested > (result['restore_tested'] or 0):
        result.update(restore_tested=tested, restore_status=metadata.get('restore_status') or 'not_tested')
    return {**result, 'archive_state': 'available', 'archive_available': row['state'] == 'verified'}


def require_available(root, row):
    if not row or not archive_info(root, dict(row))['archive_available']:
        raise ValueError('backup_unavailable')


def prune(root, days, now=None, protected=()):
    """Preserve two actually present archives; missing references never count."""
    root=Path(root);now=time.time() if now is None else now
    cutoff=now-days*86400;candidates=[]
    for path in root.glob('*.json'):
        try:
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size>65536:continue
            value=json.loads(path.read_text(encoding='utf-8'))
            created=value.get('created')
            if not isinstance(created,(float,int)) or not math.isfinite(created):continue
            if not archive_info(root,value)['archive_available']:continue
            if path.name!=value['path'][:-7]+'.json':continue
            candidates.append((value,path))
        except (OSError,ValueError,KeyError,TypeError):continue
    candidates.sort(key=lambda x:(x[0]['created'],x[0]['path']),reverse=True)
    expired=[]
    for value,path in candidates[2:]:
        if value['created']>=cutoff or value['path'] in protected:continue
        archive=root/value['path']
        if archive.is_symlink():raise RuntimeError('unsafe_backup_archive')
        archive.unlink()
        value['archive_state']='expired';Store.atomic(path,json.dumps(value).encode())
        expired.append(value['path'])
    return expired


def page(st, root, *, limit=100, cursor='', state='', kind='', after=0, before=0):
    if not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError('invalid_backup_filter')
    if state and state not in {'running', 'verified', 'failed', 'interrupted'}:
        raise ValueError('invalid_backup_filter')
    if kind and not re.fullmatch('[a-z_]{1,40}', kind):
        raise ValueError('invalid_backup_filter')
    if not all(math.isfinite(x) and x >= 0 for x in (after, before)) or (before and before < after):
        raise ValueError('invalid_backup_filter')
    filters = [state, kind, after, before]
    where, args = [], []
    for column, value in [('state', state), ('kind', kind)]:
        if value:
            where.append(column + '=?'); args.append(value)
    if after:
        where.append('created>=?'); args.append(after)
    if before:
        where.append('created<=?'); args.append(before)
    if cursor:
        try:
            if len(cursor) > 2048: raise ValueError()
            data = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
            created, identifier = data['created'], data['id']
            if data['filters'] != filters or not isinstance(created, (float, int)) or not math.isfinite(created): raise ValueError()
            if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier): raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError('invalid_backup_cursor') from None
        where.append('(created<? OR (created=? AND id<?))'); args.extend([created, created, identifier])
    query = 'SELECT * FROM backups' + (' WHERE ' + ' AND '.join(where) if where else '')
    with st.db() as db:
        records = [dict(x) for x in db.execute(query + ' ORDER BY created DESC,id DESC LIMIT ?', [*args, limit + 1])]
    more = len(records) > limit
    records = records[:limit]
    next_cursor = ''
    if more:
        last = records[-1]
        raw = json.dumps({'created': last['created'], 'id': last['id'], 'filters': filters}, separators=(',', ':')).encode()
        next_cursor = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return {'records': [{**row, **archive_info(root, row)} for row in records], 'next_cursor': next_cursor}

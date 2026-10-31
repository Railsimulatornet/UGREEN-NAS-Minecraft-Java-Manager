"""Bounded guard journal reader and transactional import into the manager history."""
import json
import math
import os
from pathlib import Path
import re
import uuid


def read_batch(path, cursor):
    path = Path(path)
    if not path.exists():
        return {'cursor': cursor, 'records': []}
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        identity = str(info.st_dev) + ':' + str(info.st_ino)
        offset = cursor.get('offset', 0) if cursor.get('identity') == identity else 0
        if not isinstance(offset, int) or not 0 <= offset <= info.st_size:
            offset = 0
        source.seek(offset)
        records = []
        for _ in range(200):
            start = source.tell()
            line = source.readline(4097)
            if not line:
                break
            if not line.endswith(b'\n'):
                # A writer may not have completed the last record yet.
                source.seek(start)
                break
            offset = source.tell()
            try:
                item = json.loads(line)
                identifier = str(uuid.UUID(item['uuid']))
                at = float(item['at'])
                if item['uuid'] != identifier or not math.isfinite(at) or at < 0:
                    continue
                if item['event'] not in ['player_login', 'player_logout','player_moderation']:
                    continue
                if not re.fullmatch('[A-Za-z0-9_]{1,16}', item['name']):
                    continue
                record={'key': identity + ':' + str(start), 'uuid': identifier,
                        'name': item['name'], 'event': item['event'], 'at': at}
                if item['event']=='player_moderation':
                    if item.get('action') not in ['kick','announce','time','weather']:continue
                    detail=item.get('detail','')
                    if not isinstance(detail,str) or len(detail)>500 or any(x in detail for x in ['\x00','\r','\n']):continue
                    if item.get('phase')!='authorized':continue
                    record.update(action=item['action'],detail=detail,phase='authorized')
                    if item.get('target_uuid'):
                        if str(uuid.UUID(item['target_uuid']))!=item['target_uuid']:continue
                        record['target_uuid']=item['target_uuid']
                records.append(record)
            except (ValueError, TypeError, KeyError):
                continue
        return {'cursor': {'identity': identity, 'offset': offset}, 'records': records}


def ingest(store, batch):
    """Commit deduplication, timestamps and the cursor together; retries are harmless."""
    arrivals=[]
    with store.db(immediate=True) as db:
        for item in batch['records']:
            inserted = db.execute('INSERT OR IGNORE INTO guard_events(key) VALUES(?)', (item['key'],))
            if inserted.rowcount != 1:
                continue
            details = {'uuid': item['uuid'], 'name': item['name']}
            if item['event']=='player_login':
                first=db.execute('INSERT OR IGNORE INTO player_greeting_history(uuid,first_seen) VALUES(?,?)',(item['uuid'],item['at'])).rowcount==1
                arrivals.append({**details,'at':item['at'],'first':first})
            if item['event']=='player_moderation':details.update({k:item[k] for k in ['action','detail','target_uuid','phase'] if k in item})
            if item['event'] == 'player_logout':
                previous = db.execute("SELECT at,event FROM events WHERE category='player' AND event IN ('player_login','player_logout') AND json_extract(data,'$.uuid')=? ORDER BY id DESC LIMIT 1", (item['uuid'],)).fetchone()
                if previous and previous['event'] == 'player_login':
                    details['session_seconds'] = max(0, item['at'] - previous['at'])
            db.execute('INSERT INTO events(at,category,event,data) VALUES(?,?,?,?)',
                       (item['at'], 'player', item['event'], json.dumps(details)))
        db.execute('INSERT INTO settings VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',
                   ('guard_event_cursor', json.dumps(batch['cursor'])))
    return arrivals

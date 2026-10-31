"""An RCON connection snapshot is authoritative; an old journal is not."""
import re
import time

def query(load):
    """Retry one read-only snapshot after a short transport/protocol failure."""
    reason=None
    for attempt in range(2):
        try:return names(load('list')),None,attempt+1
        except (OSError,RuntimeError,ValueError) as exc:
            reason=type(exc).__name__
            if isinstance(exc,RuntimeError) and str(exc)=='RCON authentication rejected':break
    return None,reason,attempt+1


def names(response):
    match = re.fullmatch(r'There are (\d+) of a max of (\d+) players online\s*:\s*(.*?)\s*', response.strip())
    if not match:
        raise ValueError('player_status_unavailable')
    result = [] if not match[3] else [x.strip() for x in match[3].split(',')]
    if len(result) != int(match[1]) or len(set(result)) != len(result) or any(not re.fullmatch('[A-Za-z0-9_]{1,16}', x) for x in result):
        raise ValueError('player_status_unavailable')
    return result


def reconcile(report, online, now=None):
    now = time.time() if now is None else now
    result = {**report, 'checked_at': now, 'source': 'minecraft_rcon' if online is not None else 'unavailable', 'online_names': online}
    result['players'] = []
    for original in report.get('players', []):
        player = dict(original)
        connected = None if online is None else player['name'] in online
        player['online'] = connected
        # Never advertise an old session as current when the server is unavailable.
        player['online_since'] = (player.get('online_since') or now) if connected else None
        if connected:
            player['last_seen'] = now
        result['players'].append(player)
    return result

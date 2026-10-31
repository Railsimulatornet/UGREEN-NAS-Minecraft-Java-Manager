"""Canonical addresses and an explicit, bounded reverse-proxy trust boundary."""
import hashlib,ipaddress,json,re,time
from urllib.parse import urlsplit

LAN=[ipaddress.ip_network(x) for x in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','fc00::/7']]

def address(value):
    try:
        parsed=urlsplit(value)
        if (not isinstance(value,str) or len(value)>300 or any(ord(c)<33 for c in value) or parsed.scheme!='https' or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('','/') or not parsed.hostname
            or not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]{1,5})?',parsed.netloc)
            or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',part) for part in parsed.hostname.split('.'))
            or parsed.port is not None and not 1<=parsed.port<=65535):raise ValueError()
        return 'https://'+parsed.netloc.lower()
    except (ValueError,TypeError,AttributeError):raise ValueError('invalid_web_address') from None

def settings(store,fallback):
    saved=store.get('web_access') or {}
    result={'address':saved.get('address',fallback),'external_web':saved.get('external_web',True)}
    pending=saved.get('pending')
    if isinstance(pending,dict) and pending.get('expires',0)>time.time():result['pending']=pending
    result['basis']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result

def configured_proxies(value):
    # Exact addresses only. A whole Docker/private subnet must never become trusted.
    if not value:return frozenset()
    try:
        values=[str(ipaddress.ip_address(x.strip())) for x in value.split(',')]
        if len(values)>10 or any(ipaddress.ip_address(x).is_unspecified or ipaddress.ip_address(x).is_multicast for x in values):raise ValueError()
        return frozenset(values)
    except ValueError:raise ValueError('invalid_trusted_proxy') from None

def configured_local_networks(value):
    if not value:return ()
    try:
        values=tuple(ipaddress.ip_network(x.strip(),strict=True) for x in value.split(','))
        if len(values)>10 or any(not any(network.subnet_of(parent) for parent in LAN if parent.version==network.version) for network in values):raise ValueError()
        return values
    except ValueError:raise ValueError('invalid_local_network') from None

def incoming(request,proxies,local_networks):
    try:peer=ipaddress.ip_address(request.client.host)
    except ValueError:return request.client.host,False
    except AttributeError:return None,False
    trusted=str(peer) in proxies
    if trusted:
        try:
            # The approved proxy overwrites this header with its actual TCP peer.
            if len(request.headers.getlist('x-real-ip'))!=1:return None,False
            client=ipaddress.ip_address(request.headers['x-real-ip'])
            if client.is_unspecified or client.is_multicast or client.is_link_local:return None,False
        except ValueError:return None,False
        return str(client),client.is_loopback or any(client in network for network in LAN if client.version==network.version)
    return str(peer),peer.is_loopback or any(peer in network for network in local_networks if peer.version==network.version)

def allowed_origins(config):
    return [config['address']]+([config['pending']['address']] if config.get('pending') else [])

def change(store,fallback,actor,desired,expected,confirmation,local,proxy_ready):
    with store.db(immediate=True) as db:
        current=settings(store,fallback)
        if current['basis']!=expected:raise ValueError('web_access_changed')
        target=address(desired['address'])
        if type(desired.get('external_web')) is not bool:raise ValueError('invalid_setting')
        if not desired['external_web'] and not local:raise ValueError('web_access_requires_local_connection')
        if not desired['external_web'] and not proxy_ready:raise ValueError('web_proxy_setup_required')
        saved={'address':current['address'],'external_web':desired['external_web']}
        if target!=current['address']:
            if confirmation!=target:raise ValueError('web_address_confirmation_required')
            saved['pending']={'address':target,'expires':time.time()+600,'actor':actor['id']}
        raw=json.dumps(saved)
        db.execute('INSERT INTO settings(name,value,secret) VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',('web_access',raw))
    store.event('system','web_access_changed',actor['id'],{'address_pending':target!=current['address'],'external_web':desired['external_web']})
    return settings(store,fallback)

def activate(store,fallback,actor,request_origin,expected):
    with store.db(immediate=True) as db:
        current=settings(store,fallback);pending=current.get('pending')
        if current['basis']!=expected or not pending or request_origin!=pending['address']:raise ValueError('web_address_not_verified')
        if pending['actor']!=actor['id']:raise ValueError('web_address_other_admin')
        saved={'address':pending['address'],'external_web':current['external_web']}
        db.execute('UPDATE settings SET value=? WHERE name=?',(json.dumps(saved),'web_access'))
    store.event('system','web_address_activated',actor['id'],{})
    return settings(store,fallback)

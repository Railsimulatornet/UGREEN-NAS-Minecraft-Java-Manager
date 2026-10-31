"""Plain-text, per-player greetings; no command or JSON interpolation."""
import json,re,time,uuid

DEFAULTS={'first_enabled':False,'return_enabled':False,
          'first_message':'Willkommen auf dem Server, {player}!',
          'return_message':'Willkommen zurück, {player}!'}

def validate(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULTS):raise ValueError('invalid_greeting_settings')
    for key in ('first_enabled','return_enabled'):
        if type(value[key]) is not bool:raise ValueError('invalid_greeting_settings')
    for key in ('first_message','return_message'):
        text=value[key]
        if not isinstance(text,str) or not text.strip() or len(text)>500 or any(ord(c)<32 and c!='\n' for c in text):raise ValueError('invalid_greeting_settings')
    return dict(value)

def send(store,rpc,arrivals,now=None):
    cfg=validate(store.get('greetings') or DEFAULTS);now=time.time() if now is None else now
    for arrival in arrivals:
        if not 0<=now-arrival['at']<=90:continue
        name=arrival['name'];identifier=arrival['uuid']
        if not re.fullmatch('[A-Za-z0-9_]{1,16}',name) or str(uuid.UUID(identifier))!=identifier:continue
        kind='first' if arrival['first'] else 'return'
        if not cfg[kind+'_enabled']:continue
        text=cfg[kind+'_message'].replace('{player}',name)
        try:
            rpc('/console',{'command':'tellraw '+name+' '+json.dumps({'text':text},ensure_ascii=False)})
            store.event('player','greeting_sent',data={'uuid':identifier,'kind':kind})
        except Exception:
            # A player may leave between the journal entry and delivery. Never
            # replay a greeting to another session or block journal processing.
            store.event('player','greeting_failed',data={'uuid':identifier,'kind':kind})

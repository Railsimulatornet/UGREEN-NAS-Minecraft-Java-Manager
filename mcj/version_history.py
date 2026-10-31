"""Bounded, read-only version-plan history; actions remain guarded by maintenance."""
import json,math,re
from . import mods

STATES={'metadata_passed','blocked','tested','failed','applied','testing'}

def history(st,query='',state='',limit=25,cursor=None):
    if len(query)>120 or state and state not in STATES or not 1<=limit<=100:
        raise ValueError('invalid_history_filter')
    where=[];args=[]
    for term in query.lower().split()[:6]:
        where.append('instr(lower(configuration),?)>0');args.append(term)
    if state:where.append('state=?');args.append(state)
    if cursor:
        try:
            created,identifier=cursor.split(':',1);created=float(created)
            if not math.isfinite(created) or created<0 or not re.fullmatch('[0-9a-f]{32}',identifier):
                raise ValueError('invalid_history_cursor')
        except ValueError:raise ValueError('invalid_history_cursor') from None
        where.append('(created<? OR (created=? AND id<?))');args.extend([created,created,identifier])
    sql='SELECT * FROM version_plans'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY created DESC,id DESC LIMIT ?'
    with st.db() as db:rows=[dict(x) for x in db.execute(sql,args+[limit+1])]
    more=len(rows)>limit;rows=rows[:limit]
    current=json.dumps(st.get('server'),sort_keys=True);fingerprint=mods.fingerprint(st);items=[]
    for row in rows:
        try:configuration=json.loads(row['configuration'])
        except (ValueError,TypeError):configuration={}
        if not isinstance(configuration,dict):configuration={}
        item={'id':row['id'],'created':row['created'],'updated':row['updated'],'state':row['state'],
              'configuration':{k:configuration.get(k) for k in ['version','java','loader','loader_version']},
              'actionable':row['state'] in {'metadata_passed','tested'} and (row['state']!='tested' or bool(row.get('image_id'))) and row['based_on']==current and row.get('mod_fingerprint')==fingerprint}
        for key in ['report','test_result']:
            try:item[key]=json.loads(row[key]) if row[key] else None
            except (ValueError,TypeError):item[key]=None
        items.append(item)
    return {'records':items,'next_cursor':str(rows[-1]['created'])+':'+rows[-1]['id'] if more else None}

"""Compare immutable exported client manifests, never capability tokens or credentials."""
import json,re,zipfile
from . import client_packs


def summary(row,manifest):
    if not isinstance(manifest.get('version'),str) or not 1<=len(manifest['version'])<=120:raise ValueError('client_pack_manifest_invalid')
    return {'id':row['id'],'number':row['number'],'created':row['created'],'size':row['size'],
            'version':manifest['version'],'runtime':client_packs.runtime(manifest['runtime'])}


def catalog(st,before=None,limit=50):
    if before is not None and before<1 or not 1<=limit<=100:raise ValueError('client_pack_invalid_page')
    sql='SELECT * FROM client_packs'+(' WHERE number<?' if before is not None else '')+' ORDER BY number DESC LIMIT ?'
    with st.db() as db:rows=[dict(x) for x in db.execute(sql,([before] if before is not None else [])+[limit+1])]
    more=len(rows)>limit;rows=rows[:limit]
    return {'records':[summary(row,json.loads(row['manifest'])) for row in rows],'next_cursor':rows[-1]['number'] if more else None}


def exported_manifest(st,identifier):
    path,row=client_packs.archive(st,identifier)
    with zipfile.ZipFile(path) as archive:
        info=archive.getinfo('overrides/MCJ-CLIENT-PACK.json')
        if info.file_size>4*1024*1024:raise ValueError('client_pack_integrity_failed')
        manifest=json.loads(archive.read(info))
    if manifest!=json.loads(row['manifest']):raise ValueError('client_pack_integrity_failed')
    return row,manifest


def components(manifest):
    result={}
    def add(record,metadata,filename,sha,category):
        items=metadata or []
        if any(not isinstance(x,dict) or any(not isinstance(x.get(k),str) or not x[k] or len(x[k])>500 for k in ['id','name','version']) for x in items):raise ValueError('client_pack_manifest_invalid')
        ids=sorted(x['id'] for x in items)
        key='mod:'+','.join(ids) if ids else 'file:'+filename
        if not ids or not re.fullmatch('[0-9a-f]{64}',sha) or key in result:raise ValueError('client_pack_manifest_invalid')
        result[key]={'id':key,'name':', '.join(str(x['name']) for x in items),'version':', '.join(str(x['version']) for x in items),'filename':filename,'sha256':sha,'category':category}
    for record in manifest.get('mods',[]):
        if record.get('client') in {'required','optional'}:add(record,record['mods'],record['filename'],record['sha256'],'mod')
    graphics=manifest.get('graphics') or {}
    for record in graphics.get('files',[]):
        path=record['path'];sha=record['hashes']['sha256']
        if path.startswith('mods/'):add(record,record['metadata']['mods'],path[5:],sha,'graphics')
        elif path.startswith('shaderpacks/'):
            if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('client_pack_manifest_invalid')
            key='shader:selected' if path=='shaderpacks/'+graphics.get('shader','') else 'shader:'+path[12:]
            result[key]={'id':key,'name':'Shaderpack','version':path[12:],'filename':path[12:],'sha256':sha,'category':'shader'}
    return result


def compare_manifests(before,after):
    old=components(before);new=components(after)
    changed=[{'id':key,'before':old[key],'after':new[key]} for key in sorted(old.keys()&new.keys()) if any(old[key][field]!=new[key][field] for field in ['sha256','filename','version'])]
    return {'added':[new[key] for key in sorted(new.keys()-old.keys())],'removed':[old[key] for key in sorted(old.keys()-new.keys())],
            'changed':changed,'unchanged':len(old.keys()&new.keys())-len(changed),
            'runtime_changed':client_packs.runtime(before['runtime'])!=client_packs.runtime(after['runtime'])}


def compare(st,before_id,after_id):
    before_row,before=exported_manifest(st,before_id);after_row,after=exported_manifest(st,after_id)
    return {'before':summary(before_row,before),'after':summary(after_row,after),**compare_manifests(before,after)}

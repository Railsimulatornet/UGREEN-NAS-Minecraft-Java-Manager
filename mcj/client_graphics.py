"""Reviewed client-only graphics; never installed in the dedicated server."""
import hashlib
import json
import re
from . import client_packs as cp


def approved(st,active):
    value=st.get('client_graphics')
    if not value:return None
    if value.get('create_compatibility_patch') and value['create_compatibility_patch']!=cp.CREATE_IRIS_HASH:raise ValueError('client_create_patch_unverified')
    if cp.runtime(value.get('runtime',{}))!=cp.runtime(active):raise ValueError('client_graphics_runtime_changed')
    files=value.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=8:raise ValueError('client_graphics_unverified')
    names=set()
    for item in files:
        path=item.get('path','')
        if not re.fullmatch(r'(mods/[A-Za-z0-9_.+()-]+\.jar|shaderpacks/[A-Za-z0-9_.+()-]+\.zip)',path) or path in names:raise ValueError('client_graphics_unverified')
        names.add(path)
        if type(item.get('fileSize')) is not int or not 0<item['fileSize']<=64*1024*1024:raise ValueError('client_graphics_unverified')
        if set(item.get('hashes',{}))!={'sha1','sha256','sha512'} or any(not re.fullmatch('[0-9a-f]{'+str(length)+'}',item['hashes'][key]) for key,length in [('sha1',40),('sha256',64),('sha512',128)]):raise ValueError('client_graphics_unverified')
        if len(item.get('downloads',[]))!=1:raise ValueError('client_graphics_unverified')
        cp.public_url(item['downloads'][0])
        if item.get('env')!={'client':'required','server':'unsupported'}:raise ValueError('client_graphics_unverified')
        if path.startswith('mods/') and item.get('metadata',{}).get('loader')!=active['loader']:raise ValueError('client_graphics_unverified')
    if 'shaderpacks/'+value.get('shader','') not in names:raise ValueError('client_graphics_unverified')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value else None


def pack_records(value):
    return [{'filename':x['path'][5:],'hashes':x['hashes'],'size':x['fileSize'],'metadata':x['metadata']} for x in value['files'] if x['path'].startswith('mods/')] if value else []

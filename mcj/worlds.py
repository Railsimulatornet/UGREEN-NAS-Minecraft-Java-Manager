"""Bounded world imports; only disposable backup candidates receive staged worlds."""
from .project_paths import project_path
import gzip
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import secrets
import shutil
import struct
import stat
import time
import zipfile

MAX_ARCHIVE=2*1024**3
MAX_EXPANDED=10*1024**3
MAX_FILES=100000


def validate_level(path,*,metadata=False,storage='level'):
    """Parse bounded Java NBT without trusting a gzip header as a valid world."""
    try:
        # Reject FIFOs through fstat instead of waiting for a writer while the
        # controller holds its maintenance locks. Regular files are unaffected.
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
        with os.fdopen(fd,'rb') as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):raise ValueError('world_level_dat_invalid')
            with gzip.GzipFile(fileobj=source,mode='rb') as level:raw=level.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError('world_level_dat_invalid')
        offset=0;tags=0;seeds={}
        def take(count):
            nonlocal offset
            if count<0 or offset+count>len(raw):raise ValueError('world_level_dat_invalid')
            value=raw[offset:offset+count];offset+=count;return value
        def number(code):return struct.unpack('>'+code,take(struct.calcsize(code)))[0]
        def text():return take(number('H')).decode('utf-8','replace')
        def payload(kind,depth,tag_path=()):
            nonlocal tags
            tags+=1
            if depth>32 or tags>1000000:raise ValueError('world_level_dat_invalid')
            scalar={1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}
            if kind in scalar:
                value=number(scalar[kind])
                if kind==4 and tag_path in [('Data','WorldGenSettings','seed'),('Data','RandomSeed'),('data','seed')]:
                    if tag_path in seeds:raise ValueError('world_level_dat_invalid')
                    seeds[tag_path]=value
                return value
            if kind==8:return text()
            if kind in [7,11,12]:
                count=number('i')
                if count<0:raise ValueError('world_level_dat_invalid')
                take(count*{7:1,11:4,12:8}[kind]);return None
            if kind==9:
                child=number('B');count=number('i')
                if count<0 or count>1000000 or (child==0 and count):raise ValueError('world_level_dat_invalid')
                for _ in range(count):payload(child,depth+1,tag_path+('[]',))
                return None
            if kind==10:
                captured={}
                while True:
                    child=number('B')
                    if child==0:return captured
                    name=text();value=payload(child,depth+1,tag_path+(name,))
                    if depth<=1:
                        if name in captured:raise ValueError('world_level_dat_invalid')
                        captured[name]=value
            raise ValueError('world_level_dat_invalid')
        if number('B')!=10:raise ValueError('world_level_dat_invalid')
        text();value=payload(10,0)
        data=value if storage=='generation' and isinstance(value.get('data'),dict) else value.get('Data')
        if offset!=len(raw) or not isinstance(data,dict) or type(data.get('DataVersion')) is not int or data['DataVersion']<=0:
            raise ValueError('world_level_dat_invalid')
        seed=seeds.get(('data','seed')) if storage=='generation' else seeds.get(('Data','WorldGenSettings','seed'),seeds.get(('Data','RandomSeed')))
        # JSON numbers cannot preserve all signed 64-bit seeds in a browser.
        if metadata:return {'data_version':data['DataVersion'],'seed':str(seed) if seed is not None else None}
        return data['DataVersion']
    except (OSError,EOFError,struct.error):raise ValueError('world_level_dat_invalid') from None


def world_seed(folder):
    """26.1+ stores generation settings separately; older worlds use level.dat."""
    folder=Path(folder);generation=folder/'data/minecraft/world_gen_settings.dat'
    if any(p.is_symlink() for p in (folder,folder/'data',folder/'data/minecraft',generation)):return None
    try:
        if generation.exists():return validate_level(generation,metadata=True,storage='generation')['seed']
        return validate_level(folder/'level.dat',metadata=True)['seed']
    except ValueError:return None


def valid_name(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',name):raise ValueError('invalid_world_name')
    return name


def require_supported_format(data,runtime,guard):
    path=Path(data)/valid_name(runtime.get('world','world'))/'level.dat'
    if not path.exists():return  # A new world will be created in the isolated test.
    expected=guard.get('minecraft_data_version')
    if type(expected) is not int or expected<1:raise ValueError('world_version_unverified')
    if validate_level(path)>expected:raise ValueError('world_newer_than_selected_server')


def inventory(server):
    result=[];budget=MAX_FILES
    for folder in sorted(Path(server).iterdir()):
        if folder.is_symlink() or not folder.is_dir() or not (folder/'level.dat').is_file() or (folder/'level.dat').is_symlink():continue
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',folder.name):continue
        size=0;complete=True
        for parent,dirs,files in os.walk(folder,followlinks=False):
            dirs[:]=[x for x in dirs if not (Path(parent)/x).is_symlink()]
            for filename in files:
                path=Path(parent)/filename
                if path.is_symlink():continue
                if budget<=0:complete=False;break
                try:size+=path.stat().st_size
                except FileNotFoundError:complete=False
                budget-=1
            if not complete:break
        seed=world_seed(folder)
        result.append({'name':folder.name,'size':size,'size_complete':complete,'source':'server','seed':seed})
        if len(result)>=100:break
    return result


def stage(store,root,archive,name):
    name=valid_name(name);root=Path(root);archive=Path(archive)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size>MAX_ARCHIVE:raise ValueError('world_archive_invalid')
    checksum=hashlib.sha256()
    with archive.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):checksum.update(block)
    identifier=checksum.hexdigest();base=project_path(root,'staging/worlds');base.mkdir(parents=True,exist_ok=True,mode=0o750)
    scratch=base/('.import-'+secrets.token_hex(16));scratch.mkdir(mode=0o700)
    try:
        with zipfile.ZipFile(archive) as z:
            entries=z.infolist()
            if not entries or len(entries)>MAX_FILES:raise ValueError('world_archive_limit')
            if sum(x.file_size for x in entries)>MAX_EXPANDED:raise ValueError('world_archive_limit')
            paths={}
            for item in entries:
                path=PurePosixPath(item.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in item.filename or ':' in item.filename or '\x00' in item.filename or len(item.filename)>500:
                    raise ValueError('world_archive_unsafe_path')
                if item.flag_bits&1 or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('world_archive_unsafe_path')
                if str(path) in paths:raise ValueError('world_archive_duplicate_path')
                paths[str(path)]=item
            roots=[PurePosixPath(x).parent for x in paths if PurePosixPath(x).name=='level.dat']
            if not roots:raise ValueError('world_level_dat_missing')
            prefix=min(roots,key=lambda x:len(x.parts))
            if len(prefix.parts)>1:raise ValueError('world_archive_layout_invalid')
            files=[];expanded=0
            for relative,item in paths.items():
                path=PurePosixPath(relative)
                if not path.is_relative_to(prefix):raise ValueError('world_archive_layout_invalid')
                path=path.relative_to(prefix)
                if item.is_dir() or str(path)=='.' or path.name=='session.lock':continue
                destination=scratch/'data'/str(path)
                destination.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
                digest=hashlib.sha256();size=0
                with z.open(item) as source,destination.open('xb') as target:
                    os.chmod(destination,0o640)
                    for block in iter(lambda:source.read(65536),b''):
                        size+=len(block);expanded+=len(block)
                        if expanded>MAX_EXPANDED:raise ValueError('world_archive_limit')
                        digest.update(block);target.write(block)
                if size!=item.file_size:raise ValueError('world_archive_invalid')
                files.append({'path':str(path),'size':size,'sha256':digest.hexdigest()})
            level_metadata=validate_level(scratch/'data/level.dat',metadata=True)
            seed=world_seed(scratch/'data')
        with store.change_lock():
            imports=store.get('world_imports') or []
            if any(x['name']==name and x['id']!=identifier for x in imports):raise ValueError('world_name_already_exists')
            if len(imports)>=100 and not any(x['name']==name for x in imports):raise ValueError('world_import_limit')
            final=base/identifier
            manifest={'id':identifier,'files':files,'size':expanded}
            manifest_raw=json.dumps(manifest,separators=(',',':')).encode()
            store.atomic(scratch/'manifest.json',manifest_raw,0o640)
            if final.exists():
                if final.is_symlink() or not (final/'manifest.json').is_file():raise ValueError('world_staging_integrity_failed')
                if json.loads((final/'manifest.json').read_text())!=manifest:raise ValueError('world_staging_integrity_failed')
            else:os.rename(scratch,final)
            record={'id':identifier,'name':name,'created':time.time(),'size':expanded,'files':len(files),'data_version':level_metadata['data_version'],'seed':seed,
                'manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),'state':'staged'}
            imports=[x for x in imports if x['name']!=name]+[record];store.set('world_imports',imports)
        return {**record,'live_server_changed':False,'runtime_test':'not_tested'}
    except (zipfile.BadZipFile,FileExistsError,IsADirectoryError,NotADirectoryError):raise ValueError('world_archive_invalid') from None
    finally:
        if scratch.exists():shutil.rmtree(scratch)


def apply_import(store,root,data,runtime):
    name=valid_name(runtime.get('world','world'));data=Path(data)
    destination=data/name
    if destination.is_symlink():raise ValueError('unsafe_world_directory')
    if destination.exists():return None
    record=next((x for x in store.get('world_imports') or [] if x['name']==name),None)
    if not record:return None  # Minecraft creates a new world during its isolated startup.
    identifier=record['id']
    if not re.fullmatch('[0-9a-f]{64}',identifier):raise ValueError('world_staging_integrity_failed')
    folder=project_path(Path(root),'staging/worlds')/identifier
    if folder.is_symlink() or (folder/'manifest.json').is_symlink() or (folder/'manifest.json').stat().st_size>32*1024*1024:raise ValueError('world_staging_integrity_failed')
    manifest_raw=(folder/'manifest.json').read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest()!=record.get('manifest_sha256'):raise ValueError('world_staging_integrity_failed')
    manifest=json.loads(manifest_raw)
    if manifest.get('id')!=identifier or len(manifest['files'])>MAX_FILES:raise ValueError('world_staging_integrity_failed')
    destination.mkdir(mode=0o750)
    for item in manifest['files']:
        relative=PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:raise ValueError('world_staging_integrity_failed')
        source=folder/'data'/str(relative)
        if any(parent.is_symlink() for parent in [source,*source.parents] if parent!=Path(root).parent):raise ValueError('world_staging_integrity_failed')
        target=destination/str(relative);target.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
        digest=hashlib.sha256();size=0
        with source.open('rb') as incoming,target.open('xb') as outgoing:
            os.chmod(target,0o640)
            for block in iter(lambda:incoming.read(65536),b''):digest.update(block);outgoing.write(block);size+=len(block)
        if size!=item['size'] or digest.hexdigest()!=item['sha256']:raise ValueError('world_staging_integrity_failed')
    return {'name':name,'import_id':identifier,'files':len(manifest['files'])}

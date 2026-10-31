"""Temporary, authenticated browser installer. No Docker access in the HTTP process."""
import hashlib,hmac,ipaddress,json,os,re,secrets,stat,time
from pathlib import Path
from typing import Literal
from cryptography.fernet import Fernet
from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse,Response
from pydantic import BaseModel,ConfigDict,Field

COOKIE='__Host-mcj-setup'
PRIVATE=[ipaddress.ip_network(v) for v in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']]
SECURITY_HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
    'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}
SETUP_ASSETS={'logo.png':'assets/final/branding/server_logo.png','landscape.webp':'assets/final/scenes/landscape_clean.webp',
    'sunset.webp':'assets/final/scenes/sunset_landscape.webp','frame.png':'assets/final/ui/frame_wide_hd.png',
    'pixelify.ttf':'assets/PixelifySans.ttf','settings.png':'assets/final/symbols/settings.png','warning.png':'assets/final/symbols/warning.png'}
SHARED_THEME_FILES={*SETUP_ASSETS.values(),'style.css','reference-v12.css',
    'assets/final/ui/panel_border_9slice.png','assets/final/ui/grass_corner_top_left.png','assets/final/ui/grass_corner_top_right.png'}
SETUP_STEPS=('checking','folders','runtime','account','starting','handover','complete')


def step_progress(phase,previous=None):
    """Completed real stages, not an estimated transfer or remaining-time percentage."""
    completed=SETUP_STEPS.index(phase) if phase in SETUP_STEPS else 0
    if phase=='failed' and isinstance(previous,dict):
        prior=previous.get('completed')
        if type(prior) is int and 0<=prior<=6:completed=prior
    return {'completed':completed,'total':6}

def private_ip(value):
    address=ipaddress.ip_address(value)
    if address.version!=4 or not any(address in network for network in PRIVATE):raise ValueError('private_address_required')
    return str(address)

def read_regular(path,limit=32768):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:raise ValueError('unsafe_setup_file')
        value=stream.read(limit+1)
        if len(value)>limit:raise ValueError('unsafe_setup_file')
        return value

def atomic(path,value,mode=0o600,owner=None):
    temporary=path.with_name(path.name+'.'+secrets.token_hex(8))
    with temporary.open('xb') as stream:
        # Queue entries can be replaced by the listener. Privileged permission
        # operations must act on the open file, never on a replaceable pathname.
        if os.name!='nt':
            os.fchmod(stream.fileno(),mode)
            if owner is not None:os.fchown(stream.fileno(),*owner)
        stream.write(value);stream.flush();os.fsync(stream.fileno())
    if os.name=='nt':temporary.chmod(mode)
    temporary.replace(path)

class SetupSelection(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    parent:int=Field(ge=0,le=9)
    backup_parent:int=Field(ge=0,le=9)
    folder:str=Field(pattern=r'^[A-Za-z0-9_-]{2,50}$')
    backup_folder:str=Field(pattern=r'^[A-Za-z0-9_-]{2,50}$')
    username:str=Field(pattern=r'^[A-Za-z0-9_.-]{2,40}$')
    email:str=Field(min_length=5,max_length=254)
    password:str=Field(min_length=12,max_length=128)
    access_mode:Literal['internal','external']='internal'
    memory_mb:int=Field(ge=4096,le=65536)
    accept_eula:bool

def selection_config(value,context):
    value=SetupSelection.model_validate(value)
    if not value.accept_eula or value.memory_mb%1024:raise ValueError('setup_selection_invalid')
    if value.memory_mb>context['maximum_memory_mb']:raise ValueError('setup_memory_unavailable')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value.email):raise ValueError('setup_email_invalid')
    parents=context['parents']
    if value.parent>=len(parents) or value.backup_parent>=len(parents):raise ValueError('setup_parent_invalid')
    root=parents[value.parent]+'/'+value.folder;backup=parents[value.backup_parent]+'/'+value.backup_folder
    if root==backup:raise ValueError('setup_paths_overlap')
    return {'root':root,'backup_root':backup,'origin':context['origin'],'username':value.username,'email':value.email,
            'accept_eula':True,'trusted_proxies':'','local_networks':context['network'],'game_bind_address':context['address'],
            'tls_mode':'selfsigned','nas_ip':context['address'],'access_mode':value.access_mode,
            'container_memory_mb':value.memory_mb,'public_game':False},value.password

def create_app(base,context,clock=time.time):
    base=Path(base);app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    sessions={};attempts={};assets=Path(__file__).parent/'static';created=context['created']
    code_hash=context['code_hash'];cipher=Fernet(read_regular(base/'queue.key',128))
    def valid(request):
        token=request.cookies.get(COOKIE,'');entry=sessions.get(token)
        if not entry or entry['expires']<clock():return None
        return entry
    def failure(code,status=400):return JSONResponse({'error':code},status_code=status,headers=SECURITY_HEADERS)
    @app.middleware('http')
    async def guard(request,call_next):
        if request.headers.get('host')!=context['origin'].split('://',1)[1]:return failure('setup_address_mismatch',421)
        public_page=request.method=='GET' and (request.url.path in {'/','/bootstrap.js','/bootstrap-i18n.js','/bootstrap.css'} or request.url.path.startswith(('/setup-assets/','/static/')))
        if clock()>created+14400 and not public_page:return failure('setup_expired_restart_from_ugos',410)
        if request.method not in {'GET','POST'}:return failure('method_not_allowed',405)
        if request.method=='POST':
            if request.headers.get('origin')!=context['origin']:return failure('csrf',403)
            limit=2048 if request.url.path=='/setup/unlock' else 32768
            raw=b''
            async for chunk in request.stream():
                raw+=chunk
                if len(raw)>limit:return failure('request_too_large',413)
            request._body=raw
            if request.url.path!='/setup/unlock':
                entry=valid(request)
                if not entry or not hmac.compare_digest(request.headers.get('x-csrf',''),entry['csrf']):return failure('authentication_required',401)
        response=await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response
    @app.exception_handler(RequestValidationError)
    async def bad_input(request,error):return failure('setup_fields_invalid')
    @app.get('/')
    async def page():
        expired=clock()>created+14400
        return FileResponse(assets/('bootstrap-expired.html' if expired else 'bootstrap.html'),media_type='text/html',status_code=410 if expired else 200)
    @app.get('/setup-assets/{name}')
    async def graphic(name:str):
        if name not in SETUP_ASSETS:return failure('not_found',404)
        return FileResponse(assets/SETUP_ASSETS[name])
    @app.get('/static/{path:path}')
    async def shared_theme(path:str):
        # The installer reuses the real manager theme, with a fixed public file list.
        if path not in SHARED_THEME_FILES:return failure('not_found',404)
        return FileResponse(assets/path)
    @app.get('/bootstrap.js')
    async def script():return FileResponse(assets/'bootstrap.js',media_type='application/javascript')
    @app.get('/bootstrap-i18n.js')
    async def translations():return FileResponse(assets/'bootstrap-i18n.js',media_type='application/javascript')
    @app.get('/bootstrap.css')
    async def style():return FileResponse(assets/'bootstrap.css',media_type='text/css')
    @app.post('/setup/unlock')
    async def unlock(request:Request):
        address=request.client.host if request.client else 'unknown';now=clock()
        for key in [key for key,value in attempts.items() if value[0]<now-900]:attempts.pop(key,None)
        for key in [key for key,value in sessions.items() if value['expires']<now]:sessions.pop(key,None)
        # Bounded global and per-address budgets; no unbounded keys from forged sources.
        for key,limit in [('all',30),(address,8)]:
            start,count=attempts.get(key,(now,0))
            if count>=limit:return failure('setup_wait_15_minutes',429)
        try:value=await request.json();code=value.get('code','')
        except (ValueError,AttributeError):return failure('setup_code_invalid',401)
        for key in {'all',address}:
            start,count=attempts.get(key,(now,0));attempts[key]=(start,count+1)
        if not isinstance(code,str) or not hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(),code_hash):return failure('setup_code_invalid',401)
        if len(sessions)>=16:return failure('setup_session_limit',429)
        token=secrets.token_urlsafe(32);entry={'csrf':secrets.token_urlsafe(32),'expires':now+1800};sessions[token]=entry
        response=JSONResponse({'csrf':entry['csrf']});response.set_cookie(COOKIE,token,max_age=1800,secure=True,httponly=True,samesite='strict',path='/');return response
    @app.get('/setup/state')
    async def state(request:Request):
        entry=valid(request)
        if not entry:return failure('authentication_required',401)
        result=json.loads(read_regular(base/'status.json'))
        return dict(result,csrf=entry['csrf'],parents=context['parents'],maximum_memory_mb=context['maximum_memory_mb'],
                    recommended_memory_mb=context['recommended_memory_mb'],origin=context['origin'],network=context['network'])
    @app.post('/setup/install')
    async def submit(value:SetupSelection):
        try:selection_config(value.model_dump(),context)
        except ValueError:return failure('setup_selection_invalid')
        state=json.loads(read_regular(base/'status.json'))
        if state['phase'] not in {'ready','failed'} or (base/'request.fernet').exists() or (base/'active.fernet').exists():return failure('setup_already_running',409)
        # Password never goes to environment, argv, logs or a plaintext job file.
        payload=cipher.encrypt(json.dumps(value.model_dump()).encode())
        target=base/'request.fernet'
        try:
            with target.open('xb') as stream:stream.write(payload)
            target.chmod(0o600)
        except FileExistsError:return failure('setup_already_running',409)
        return {'accepted':True}
    @app.get('/setup/report')
    async def report(request:Request):
        if not valid(request):return failure('authentication_required',401)
        result=json.loads(read_regular(base/'status.json'))
        return Response(json.dumps(result,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="Minecraft-Java-Manager-Einrichtungsbericht.json"'})
    return app

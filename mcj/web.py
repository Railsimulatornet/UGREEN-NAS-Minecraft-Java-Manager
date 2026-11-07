from .project_paths import project_path
import asyncio
from contextlib import asynccontextmanager
import csv
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
import zipfile
from urllib.parse import urlparse
from typing import Literal
import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool
from . import __version__
from . import auth, mods, versions, player_events, server_settings, dispatch, runtime_state, sources, packs, worlds, automatic, backup_inventory
from . import client_packs, job_control, ui_preferences, version_history, client_pack_compare, storage_preflight
from . import mod_versions,web_access
from .notify import send_email,send_discord,discord_url
from .store import Store,HASHER


def create_app(state=None,keyfile=None,root=None,origin=None,start_worker=True):
    root=Path(root or os.environ.get('PROJECT_ROOT','/project'))
    st=Store(state or project_path(root,'state'),keyfile or '/run/secrets/encryption',os.environ.get('BOOTSTRAP_FILE'))
    if start_worker:
        from .guard_bundle import read as bundled_guards
        st.set('guard_catalog',bundled_guards())
    origin=(origin or os.environ.get('APP_ORIGIN','http://localhost:18090')).rstrip('/')
    proxy_addresses=web_access.configured_proxies(os.environ.get('MCJ_TRUSTED_PROXIES',''))
    local_networks=web_access.configured_local_networks(os.environ.get('MCJ_LOCAL_NETWORKS',''))
    def connection_policy():
        saved=st.get('connection_policy')
        if not isinstance(saved,dict):return proxy_addresses,local_networks
        return web_access.configured_proxies(saved['proxies']),web_access.configured_local_networks(saved['networks'])
    def canonical_origin():return web_access.settings(st,origin)['address']
    rpc_secret=os.environ.get('RPC_SECRET','/run/secrets/rpc')
    rpc_token=Path(rpc_secret).read_text().strip() if Path(rpc_secret).exists() else None
    worker_stop=threading.Event()
    job_lock=threading.Lock()
    upload_lock=asyncio.Lock()

    def rpc(path,payload=None):
        if not rpc_token:raise RuntimeError('Controller secret unavailable')
        with httpx.Client(base_url=os.environ.get('CONTROLLER_URL','http://controller:9091'),
                          timeout=httpx.Timeout(1200,connect=5),follow_redirects=False,
                          headers={'Authorization':'Bearer '+rpc_token}) as client:
            response=client.get(path) if payload is None else client.post(path,json=payload)
            if response.status_code!=200:
                try:reason=response.json().get('reason',response.json().get('detail','controller_unavailable'))
                except ValueError:reason='controller_unavailable'
                raise RuntimeError(reason)
            return response.json()

    def finish_job(identifier,state,result):
        with st.db(immediate=True) as db:
            previous=db.execute('SELECT result FROM jobs WHERE id=?',(identifier,)).fetchone()
            progress=json.loads(previous['result']) if previous and previous['result'] else {}
            if isinstance(result,dict):result={**{k:v for k,v in progress.items() if k in ['started','phases','dependency_report']},**result}
            db.execute('UPDATE jobs SET state=?,result=?,updated=? WHERE id=?',(state,json.dumps(result),time.time(),identifier))

    def remember_players(report):
        with st.db() as db:
            for player in report.get('players',[]):
                identifier=player.get('uuid','')
                try:
                    if str(uuid.UUID(identifier))!=identifier:continue
                except (ValueError,TypeError,AttributeError):continue
                if not isinstance(player.get('name'),str) or not re.fullmatch('[A-Za-z0-9_]{1,16}',player['name']):continue
                def timestamp(value,fallback=None):return value if type(value) in (int,float) and math.isfinite(value) and value>=0 else fallback
                play=player.get('play_seconds',0)
                if type(play) not in (int,float) or not math.isfinite(play) or play<0:continue
                db.execute('''INSERT INTO players(uuid,name,first_seen,last_seen,online_since,play_seconds)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(uuid) DO UPDATE SET name=excluded.name,last_seen=excluded.last_seen,
                    online_since=excluded.online_since,play_seconds=excluded.play_seconds''',
                    (identifier,player['name'],timestamp(player.get('first_seen'),time.time()),timestamp(player.get('last_seen')),
                     timestamp(player.get('online_since')),int(play)))

    def execute_job(job):
        with job_control.operation(st,job['id']):return _execute_job(job)

    def _execute_job(job):
        try:
            with st.db(immediate=True) as db:
                fresh=db.execute("SELECT * FROM jobs WHERE id=? AND state='queued' AND approved=1",(job['id'],)).fetchone()
                if fresh is None:return
                job=dict(fresh);payload=json.loads(job['payload'])
                if job['actor'] is not None:
                    actor=db.execute('SELECT enabled,admin FROM users WHERE id=?',(job['actor'],)).fetchone()
                    if not actor or not actor['enabled'] or not actor['admin']:raise ValueError('job_actor_no_longer_authorized')
                claimed=db.execute("UPDATE jobs SET state=?,updated=? WHERE id=? AND state='queued' AND approved=1",('running',time.time(),job['id']))
                if claimed.rowcount!=1:return
            job_control.phase('preparing')
            if job['kind']=='backup':
                backup_id=secrets.token_hex(16)
                with st.db() as db:db.execute('INSERT INTO backups(id,created,kind,state) VALUES(?,?,?,?)',
                    (backup_id,time.time(),payload.get('kind','manual'),'running'))
                try:
                    result=rpc('/backup',{'kind':payload.get('kind','manual')})
                    with st.db() as db:
                        db.execute('UPDATE backups SET state=?,path=?,size=?,sha256=?,verified=? WHERE id=?',
                            ('verified',result['path'],result['size'],result['sha256'],result['verified'],backup_id))
                    st.event('backup','backup_verified',job['actor'],{'id':backup_id,'size':result['size']})
                except Exception as exc:
                    with st.db() as db:db.execute('UPDATE backups SET state=?,error=? WHERE id=?',('failed',str(exc)[:250],backup_id))
                    st.event('backup','backup_failed',job['actor'],{'id':backup_id});raise
            elif job['kind']=='server':
                result=rpc('/server',{'operation':payload['operation'],'job_id':job['id']})
                st.event('server','server_'+payload['operation'],job['actor'])
            elif job['kind']=='mod_check':
                sources.check_updates(st);result={'ok':True,'automatic':automatic.stage_updates(st,root,rpc,add_job)}
            elif job['kind']=='curseforge_install':
                job_control.phase('downloading_mods')
                staged=sources.stage_curseforge_selection(st,root,payload['project_id'],payload['file_id'],payload['basis'])
                if all(item.get('installed') for item in staged):result={'state':'already_installed','staged':staged,'live_configuration_changed':False}
                else:
                    selected=[item['id'] for item in staged]
                    result=rpc('/mods/apply',{'actor':job['actor'],'fingerprint':mods.fingerprint(st),'selection':selected,'job_id':job['id']})
            elif job['kind']=='client_pack_build':
                result=client_packs.build(st,app.state.rpc,job['actor'])
            elif job['kind']=='mod_version':
                result=mod_versions.stage(st,root,payload['id'],payload['version'],payload['basis'],payload.get('pin',True))
            elif job['kind'] in ['source_check','source_stage']:
                if job['kind']=='source_check':result=sources.check_source(st,payload['id'])
                else:
                    source=sources.find_source(st,payload['id'])
                    result=sources.stage_source(st,root,source)
                    with st.change_lock():
                        current=st.get('mod_sources') or []
                        for item in current:
                            if item['id']==source['id']:item['staged']={'at':time.time(),'files':len(result['staged']),'job':job['id']}
                        st.set('mod_sources',current)
                    st.event('mods','source_staged',job['actor'],{'source_id':source['id'],'files':len(result['staged'])})
            elif job['kind']=='restore_test':
                with st.db() as db:backup=db.execute('SELECT * FROM backups WHERE id=?',(payload['id'],)).fetchone()
                backup_inventory.require_available(Path(os.environ.get('BACKUP_ROOT','/backups')),backup)
                try:result=rpc('/backup/test',{'archive':backup['path'],'job_id':job['id']})
                except Exception:
                    with st.db() as db:db.execute('UPDATE backups SET restore_tested=?,restore_status=? WHERE id=?',
                        (time.time(),'failed',backup['id']))
                    st.event('backup','restore_test_failed',job['actor'],{'id':backup['id']});raise
                with st.db() as db:db.execute('UPDATE backups SET restore_tested=?,restore_status=? WHERE id=?',
                    (time.time(),'isolated_server_verified',backup['id']))
                st.event('backup','restore_test_passed',job['actor'],{'id':backup['id'],'network':'none'})
            elif job['kind'] in ['version_test','version_apply']:
                result=rpc('/version/'+('test' if job['kind']=='version_test' else 'apply'),{'plan_id':payload['id'],'actor':job['actor'],'job_id':job['id']})
            elif job['kind'] in ['world_change','world_delete','world_export']:
                result=rpc('/world/operation',{'operation':job['kind'].split('_',1)[1],**{k:v for k,v in payload.items() if k in ['name','configuration','create']},'actor':job['actor'],'job_id':job['id']})
            elif job['kind']=='server_settings':
                result=rpc('/settings/apply',{'configuration':payload['configuration'],'based_on':payload['based_on'],'include_pending_mods':payload.get('include_pending_mods',False),'mod_fingerprint':payload.get('mod_fingerprint'),'guard_sha256':payload.get('guard_sha256'),'actor':job['actor'],'job_id':job['id']})
            elif job['kind']=='apply_mods':
                if payload.get('automatic'):
                    folder=payload.get('automatic_scope')=='folder'
                    approval=st.get('folder_mod_approval' if folder else 'automatic_mod_approval') or {}
                    ready=rpc('/maintenance-readiness')
                    if not st.get('maintenance').get('folder_automatic' if folder else 'automatic') or approval.get('actor')!=job['actor']:raise ValueError('automatic_maintenance_disabled')
                    if folder and approval!=payload.get('folder_approval'):raise ValueError('automatic_maintenance_disabled')
                    if not ready.get('ready') or folder and ready.get('visitor_verified') is not True:raise ValueError('automatic_mod_maintenance_requires_verified_guard')
                request={'actor':job['actor'],'fingerprint':payload['fingerprint'],'job_id':job['id']}
                if payload.get('automatic_scope')=='folder':request['selection']=payload['selection']
                result=rpc('/mods/apply',request)
            elif job['kind']=='restore':
                with st.db() as db:backup=db.execute('SELECT * FROM backups WHERE id=?',(payload['id'],)).fetchone()
                backup_inventory.require_available(Path(os.environ.get('BACKUP_ROOT','/backups')),backup)
                result=rpc('/backup/restore',{'archive':backup['path'],'actor':job['actor'],'job_id':job['id']})
                with st.db() as db:db.execute('UPDATE backups SET restored=? WHERE id=?',(time.time(),backup['id']))
                st.event('backup','backup_restored',job['actor'],{'id':backup['id']})
            else:
                finish_job(job['id'],'blocked',{'reason':'validation_adapter_required'});return
            finish_job(job['id'],'succeeded',result)
        except Exception as exc:
            finish_job(job['id'],'failed',{'reason':str(exc)[:250] if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__})
            st.event('maintenance','job_failed',job['actor'],{'job':job['id'],'kind':job['kind']})

    def add_job(kind,payload,actor,mode='manual',approved=True):
        identifier=secrets.token_hex(16);now=time.time()
        if kind=='apply_mods':payload={**payload,'fingerprint':mods.fingerprint(st)}
        payload=json.dumps(payload,sort_keys=True)
        # BEGIN IMMEDIATE makes duplicate submissions from different tabs/processes atomic.
        with st.db(immediate=True) as db:
            for previous in db.execute("SELECT id,payload FROM jobs WHERE kind=? AND state IN ('planned','queued','running')",(kind,)):
                if job_control.identity(db,kind,json.loads(previous['payload']))==job_control.identity(db,kind,json.loads(payload)):return previous['id']
            db.execute('INSERT INTO jobs(id,kind,state,created,updated,actor,mode,payload,result,approved) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (identifier,kind,'queued' if approved else 'planned',now,now,actor,mode,payload,None,int(approved)))
        st.event('maintenance','job_queued',actor,{'job':identifier,'kind':kind,'mode':mode})
        return identifier

    def worker():
        while job_control.deployment_held(st):
            if worker_stop.wait(1):return
        job_control.deduplicate_pending(st)
        with st.db() as db:
            db.execute("UPDATE jobs SET state='interrupted',updated=? WHERE state='running'",(time.time(),))
            db.execute("UPDATE backups SET state='interrupted',error='process_interrupted' WHERE state='running'")
        last_scan=0;last_runtime_cleanup=0
        while not worker_stop.wait(2):
            try:
                if job_control.deployment_held(st):continue
                if time.time()-last_scan>30:
                    server=st.get('server')
                    if server.get('loader')=='FABRIC' and ((st.get('loader_components') or {}).get(server['loader_version']) or st.rate('loader-metadata:'+server['loader_version'],1,300)):
                        try:versions.ensure_loader_components(st,server['loader_version'])
                        except Exception as exc:
                            if st.rate('loader-metadata-error',1,300):st.event('mods','loader_metadata_failed',data={'error_class':type(exc).__name__})

                    try:
                        remember_players(rpc('/players'))
                        from . import greetings
                        arrivals=player_events.ingest(st,rpc('/player-events',{'cursor':st.get('guard_event_cursor') or {}}))
                        greetings.send(st,rpc,arrivals)
                    except Exception:pass
                    last_scan=time.time()
                cfg=st.get('maintenance')
                if cfg.get('folder_scan_enabled',True) and time.time()-(st.get('folder_scan_last') or 0)>=cfg.get('folder_check_minutes',30)*60:
                    mods.scan_drop_folder(st,root)
                    st.set('folder_scan_last',time.time())
                    automatic.stage_folder_mods(st,root,rpc,add_job)
                with st.db() as db:
                    backup_at=db.execute("SELECT MAX(created) FROM jobs WHERE kind='backup'").fetchone()[0]
                    checked_at=db.execute("SELECT MAX(created) FROM jobs WHERE kind='mod_check'").fetchone()[0]
                    queued=[dict(x) for x in db.execute("SELECT * FROM jobs WHERE state='queued' AND approved=1 ORDER BY created")]
                # The first backup is scheduled after a complete interval, not during initial setup.
                from .backup_schedule import enqueue_due
                enqueue_due(st,add_job)
                if time.time()-(checked_at or app.state.started)>cfg['check_minutes']*60:
                    add_job('mod_check',{},None)
                if not queued and (st.get('runtime_cleanup') or {}).get('enabled') and time.time()-last_runtime_cleanup>=3600:
                    last_runtime_cleanup=time.time()
                    rpc('/runtime-files/cleanup',{})
                for job in queued:
                    scheduled=json.loads(job['payload']).get('_scheduled_at')
                    if scheduled and time.time()<scheduled:continue
                    if job['mode'] in ['idle_now','idle_5min','scheduled']:
                        status=rpc('/status')
                        if status.get('players_online')!=0:
                            with st.db() as db:db.execute('UPDATE jobs SET updated=? WHERE id=?',(time.time(),job['id']))
                            continue
                        if job['mode']=='idle_5min' and time.time()-job['updated']<300:continue
                    with job_lock:execute_job(job)
                    break
            except Exception as exc:
                # Avoid leaking remote exceptions, credentials or support tracebacks.
                if st.rate('worker-error:'+type(exc).__name__,1,300):
                    st.event('system','worker_error',data={'error_class':type(exc).__name__})

    def notification_worker():
        while job_control.deployment_held(st):
            if worker_stop.wait(1):return
        dispatch.recover_inflight(st);status_at=0;history_at=0
        while not worker_stop.wait(2):
            try:
                if job_control.deployment_held(st):continue
                if time.time()-history_at>=60:
                    from . import event_history
                    event_history.run_due(st);history_at=time.time()
                dispatch.queue_events(st);dispatch.dispatch_one(st,canonical_origin())
                cfg=st.get('discord')
                if cfg.get('enabled') and 'status' in cfg.get('events',[]) and time.time()-status_at>=60:
                    status_at=time.time();dispatch.update_status(st,rpc('/status'))
            except Exception as exc:
                if st.rate('notification-worker:'+type(exc).__name__,1,300):
                    st.event('email','notification_worker_failed',data={'error_class':type(exc).__name__})

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            if not job_control.deployment_held(st):dispatch.queue_events(st)
            thread=threading.Thread(target=worker,daemon=True,name='mcj-worker');thread.start()
            threading.Thread(target=notification_worker,daemon=True,name='mcj-notifications').start()
        yield
        worker_stop.set()

    app=FastAPI(title='MCJ Manager',version=__version__,docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store=st;app.state.origin=origin;app.state.started=time.time();app.state.rpc=rpc
    app.state.add_job=add_job;app.state.execute_job=execute_job

    @app.middleware('http')
    async def security(request,call_next):
        config=web_access.settings(st,origin)
        current_proxies,current_networks=connection_policy()
        request.state.client_address,request.state.local_connection=web_access.incoming(request,current_proxies,current_networks)
        if request.state.client_address is None:return JSONResponse({'detail':'invalid_client_address'},status_code=403)
        # Health checks remain tied to the installation address and local process.
        health=request.url.path=='/healthz' and request.client.host in ('127.0.0.1','::1')
        if not health and not config['external_web'] and not request.state.local_connection:
            return JSONResponse({'detail':'external_web_disabled'},status_code=403)
        host=request.headers.get('host','')
        requested=next((value for value in web_access.allowed_origins(config) if urlparse(value).netloc==host),None)
        if requested is None and not (health and host==urlparse(origin).netloc):return JSONResponse({'detail':'invalid_host'},status_code=400)
        request.state.request_origin=requested or origin
        app.state.origin=config['address']
        if request.method in ['GET','HEAD'] and request.url.path.startswith('/api/') and request.url.path not in ['/api/auth/me','/api/settings'] and job_control.deployment_held(st):
            return JSONResponse({'detail':'application_update_running'},status_code=503,headers={'Retry-After':'5'})
        if request.method not in ['GET','HEAD','OPTIONS']:
            if request.headers.get('origin')!=request.state.request_origin:return JSONResponse({'detail':'invalid_origin'},status_code=403)
            if job_control.deployment_held(st):return JSONResponse({'detail':'application_update_running'},status_code=503,headers={'Retry-After':'5'})
            if request.url.path not in ['/api/auth/login','/api/auth/forgot','/api/auth/reset','/api/auth/reset/context','/api/auth/reset/email-challenge','/api/auth/recovery/complete','/client-pack/info','/client-pack/download']:
                raw=request.cookies.get(auth.COOKIE,'')
                if not raw or not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),st.digest('csrf:'+raw)):
                    return JSONResponse({'detail':'csrf_failed'},status_code=403)
            streaming=request.url.path in ['/api/packs/upload','/api/worlds/upload']
            limit=(packs.MAX_ARCHIVE if request.url.path=='/api/packs/upload' else 2*1024**3) if streaming else 128*1024*1024 if request.url.path=='/api/mods/upload' else 65536
            if streaming or request.url.path=='/api/mods/upload':
                try:upload_actor=auth.account(request,verified=True,admin=True)
                except HTTPException as exc:return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
                if not st.rate('upload:'+str(upload_actor['id']),4,60):return JSONResponse({'detail':'rate_limited'},status_code=429)
            try:length=int(request.headers.get('content-length','0'))
            except ValueError:return JSONResponse({'detail':'invalid_length'},status_code=400)
            if length>limit:return JSONResponse({'detail':'request_too_large'},status_code=413)
            if streaming:
                request.state.upload_limit=limit
                return await call_next(request)
            chunks=[];total=0
            async for chunk in request.stream():
                total+=len(chunk)
                if total>limit:return JSONResponse({'detail':'request_too_large'},status_code=413)
                chunks.append(chunk)
            request._body=b''.join(chunks)
            chunks.clear()
        response=await call_next(request)
        return response

    @app.middleware('http')
    async def upload_serialization(request,call_next):
        if request.method=='POST' and request.url.path in ['/api/mods/upload','/api/packs/upload','/api/worlds/upload']:
            if upload_lock.locked():return JSONResponse({'detail':'upload_busy'},status_code=409)
            async with upload_lock:return await call_next(request)
        return await call_next(request)

    @app.middleware('http')
    async def response_headers(request,call_next):
        # This outer layer also covers rejected origins, oversized uploads and other early exits.
        response=await call_next(request)
        response.headers.update({'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
            'Permissions-Policy':'camera=(), microphone=(), geolocation=()','Cache-Control':'no-store'})
        # Generic theme artwork can be revalidated with ETag without downloading it again.
        # HTML, scripts, APIs and every capability-bearing response remain no-store.
        if request.method in ['GET','HEAD'] and request.url.path.startswith('/static/assets/') and Path(request.url.path).suffix.lower() in {'.png','.webp','.jpg','.jpeg','.svg','.ttf','.woff','.woff2'} and response.status_code in [200,304]:
            response.headers['Cache-Control']='private, max-age=0, must-revalidate'
        if canonical_origin().startswith('https://'):response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    app.include_router(auth.router)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,exc):
        # Pydantic's default response can echo passwords or other sensitive inputs.
        return JSONResponse({'detail':'invalid_request'},status_code=422)

    def user(request,admin=False):return auth.account(request,verified=True,admin=admin)

    from . import setup_wizard

    @app.get('/api/setup')
    def installation_setup(request:Request):
        user(request,admin=True)
        return setup_wizard.status(st,web_access.settings(st,origin)['address'])

    @app.post('/api/setup')
    def installation_setup_progress(data:setup_wizard.Progress,request:Request):
        actor=user(request,admin=True)
        try:setup_wizard.advance(st,data,actor['id'])
        except ValueError as exc:auth.error(str(exc),409)
        return setup_wizard.status(st,web_access.settings(st,origin)['address'])

    @app.get('/healthz')
    def health():return {'version':__version__,'state':st.get('release').get('status','internal_validation')}

    @app.get('/api/overview')
    def overview(request:Request):
        actor=user(request)
        try:status=rpc('/status')
        except Exception as exc:status={'container_status':'unavailable','players_online':None,'reason':type(exc).__name__}
        configured=st.get('server')
        if not actor['admin']:
            from .public_views import runtime
            configured=runtime(configured)
        return {'status':status,'server':configured,'configuration_consistency':runtime_state.compare(configured,status.get('runtime')),'release':st.get('release'),'version':__version__,
                'copyright':'Copyright © Roman Glos 2026','affiliation':'independent_project'}

    @app.get('/api/versions')
    def version_catalog(request:Request):
        actor=user(request)
        with st.db() as db:plans=[dict(x) for x in db.execute('SELECT * FROM version_plans ORDER BY created DESC LIMIT 30')]
        for plan in plans:
            for field in ['configuration','report','test_result']:plan[field]=json.loads(plan[field]) if plan[field] else None
        current=st.get('server')
        if not actor['admin']:
            from .public_views import runtime,plan as public_plan
            current=runtime(current);plans=[public_plan(plan) for plan in plans]
        from .compatibility import matrix
        return {'current':current,'catalog':st.get('version_catalog'),'plans':plans,'automatic_minecraft_upgrades':False,'compatibility':matrix(st)}

    @app.get('/api/versions/history')
    def version_plan_history(request:Request,q:str='',state:str='',limit:int=25,cursor:str|None=None):
        user(request,admin=True)
        if cursor is not None and len(cursor)>120:auth.error('invalid_history_cursor',422)
        try:return version_history.history(st,q,state,limit,cursor)
        except ValueError as exc:auth.error(str(exc),422)

    @app.post('/api/versions/check')
    def version_refresh(request:Request):
        actor=user(request,admin=True)
        if not st.rate('versions-check',2,60):auth.error('rate_limited',429)
        return versions.refresh(st)

    @app.get('/api/versions/local')
    def local_versions(request:Request):
        user(request,admin=True)
        from .runtime_storage import cleanup_policy
        return {**app.state.rpc('/runtime-files'),'cleanup':cleanup_policy(st.get('runtime_cleanup')),'cleanup_last':st.get('runtime_cleanup_last')}

    class RuntimeCleanupPolicy(BaseModel):
        enabled:bool=Field(default=False,strict=True)
        retention_days:int=Field(default=14,ge=1,le=365,strict=True)

    @app.post('/api/versions/local/cleanup-policy')
    def local_version_cleanup_policy(data:RuntimeCleanupPolicy,request:Request):
        actor=user(request,admin=True)
        from .runtime_storage import cleanup_policy
        value=cleanup_policy(data.model_dump())
        with st.change_lock():
            st.set('runtime_cleanup',value)
            st.set('runtime_cleanup_approval',{'actor':actor['id'],'at':time.time()} if value['enabled'] else None)
        st.event('settings','runtime_cleanup_policy_updated',actor['id'],value)
        return {'policy':value,'ok':True}

    class DeleteRuntime(BaseModel):
        id:str=Field(pattern='^[0-9a-f]{32}$')
        confirmation:str|None=Field(default=None,max_length=64)
    @app.post('/api/versions/local/delete')
    def local_version_delete(data:DeleteRuntime,request:Request):
        actor=user(request,admin=True)
        try:return rpc('/runtime-files/delete',{**data.model_dump(),'actor':actor['id']})
        except (ValueError,RuntimeError) as exc:auth.error(str(exc),409)

    @app.get('/api/versions/neoforge')
    def neoforge_catalog(request:Request,minecraft:str):
        actor=user(request,admin=True)
        if not st.rate('neoforge-catalog:'+str(actor['id']),20,60):auth.error('rate_limited',429)
        try:return versions.neoforge_catalog(st,minecraft)
        except ValueError as exc:auth.error(str(exc),409)
        except (httpx.HTTPError,OSError):auth.error('loader_catalog_unavailable',503)

    class VersionPlan(BaseModel):
        version:str=Field(pattern=r'^\d+(?:\.\d+){1,2}$')
        java:int=Field(ge=17,le=25)
        loader:str=Field(pattern='^(FABRIC|FORGE|NEOFORGE)$')
        loader_version:str=Field(default='',max_length=40)
        memory_mb:int|None=Field(default=None,ge=1024,le=6144)
        properties:dict|None=None
    @app.post('/api/versions/plan')
    def version_plan(data:VersionPlan,request:Request):
        actor=user(request,admin=True)
        if not st.rate('versions-plan',4,60):auth.error('rate_limited',429)
        try:return versions.create_plan(st,data.model_dump(exclude_none=True),actor['id'])
        except ValueError as exc:auth.error(str(exc),409)

    @app.get('/api/profile/ui-preferences')
    def own_ui_preferences(request:Request):
        actor=user(request,admin=True)
        return ui_preferences.own(st,actor['id'])

    @app.post('/api/profile/ui-preferences')
    def save_own_ui_preferences(data:ui_preferences.Preferences,request:Request):
        actor=user(request,admin=True)
        st.set('admin_ui_preferences:'+str(actor['id']),data.model_dump())
        return data.model_dump()

    @app.get('/api/server/settings')
    def server_settings_get(request:Request):
        actor=user(request,admin=True)
        properties=rpc('/properties')
        try:memory=app.state.rpc('/memory-budget')
        except Exception:memory=None
        protected={**server_settings.PROTECTED,'pause-when-empty-seconds':'0'}
        return {'properties':{k:v for k,v in properties.items() if k not in server_settings.SECRET_KEYS},
                'protected':list(protected),'current':st.get('server'),'basis':hashlib.sha256(json.dumps(st.get('server'),sort_keys=True).encode()).hexdigest(),'restart_required':True,
                'ui_preferences':ui_preferences.own(st,actor['id']),'memory':memory}

    @app.get('/api/players')
    def players(request:Request):
        user(request)
        history_pending=False
        for attempt in range(2):
            try:report=app.state.rpc('/players');break
            except Exception as exc:report={'source':'unavailable','presence_error_class':type(exc).__name__}
        if report.get('online_names') is None and st.rate('presence-unavailable',1,300):
            st.event('system','player_presence_unavailable',data={'error_class':report.get('presence_error_class') or 'Unavailable','attempts':report.get('presence_attempts',attempt+1)})
        if report.get('online_names') is not None:
            try:remember_players(report)
            except Exception:
                # A history/database write failure must not discard a successful
                # authoritative RCON connection snapshot.
                history_pending=True
        with st.db() as db:known=[dict(x) for x in db.execute('SELECT * FROM players ORDER BY name')]
        online=report.get('online_names')
        for player in known:
            player['online']=None if online is None else player['name'] in online
            if player['online'] is not True:
                # Keep already observed play time, without counting an unobserved
                # outage as connected time or allowing the UI total to jump back.
                started=player.get('online_since');observed=player.get('last_seen')
                if type(started) in (int,float) and type(observed) in (int,float) and 0<started<=observed<=time.time():
                    player['play_seconds']+=max(0,observed-started)
                player['online_since']=None
        return {'players':known,'source':report.get('source','unavailable'),'checked_at':report.get('checked_at'),
                'online_count':len(online) if online is not None else None,'history_update_pending':history_pending}

    class PlayerAction(BaseModel):
        uuid:str=Field(min_length=36,max_length=36)
        action:str=Field(pattern='^(role|kick|ban|unban|whitelist|op)$')
        role:str=Field(default='visitor',pattern='^(visitor|player|moderator|administrator)$')
        enabled:bool=False
        reason:str=Field(default='',max_length=150)

    @app.get('/api/players/permissions')
    def player_permissions(request:Request):
        user(request,admin=True)
        return rpc('/role-permissions')

    class RolePermissions(BaseModel):roles:dict
    @app.post('/api/players/permissions')
    def player_permissions_update(data:RolePermissions,request:Request):
        actor=user(request,admin=True)
        from .role_permissions import normalize
        try:value=normalize(data.roles)
        except ValueError as exc:auth.error(str(exc),409)
        result=rpc('/role-permissions',{'roles':value})
        st.event('audit','minecraft_permissions_updated',actor['id'],{'roles':value})
        return result

    @app.post('/api/players/action')
    def player_action(data:PlayerAction,request:Request):
        actor=user(request,admin=True)
        result=rpc('/player',data.model_dump())
        if result.get('grant'):
            grant=result['grant']
            with st.db() as db:
                db.execute('''INSERT INTO players(uuid,name,first_seen,role,banned,ban_reason,whitelisted,op)
                     VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(uuid) DO UPDATE SET role=excluded.role,banned=excluded.banned,
                     ban_reason=excluded.ban_reason,whitelisted=excluded.whitelisted,op=excluded.op''',
                     (data.uuid,result['name'],time.time(),grant['role'],int(grant.get('banned',False)),grant.get('reason',''),
                      int(grant.get('whitelisted',False)),int(grant.get('op',False))))
        st.event('player','player_'+data.action,actor['id'],{'uuid':data.uuid,'role':data.role if data.action=='role' else None,
                    'enabled':data.enabled if data.action in ['op','whitelist'] else None,'reason':data.reason if data.action in ['ban','unban','kick'] else None})
        return result

    class Console(BaseModel):command:str=Field(min_length=1,max_length=2000)

    from . import game_rules

    @app.get('/api/server/game-rules')
    def read_game_rules(request:Request):
        user(request,admin=True)
        return app.state.rpc('/game-rules')

    @app.post('/api/server/game-rules')
    def save_game_rule(data:game_rules.Change,request:Request):
        actor=user(request,admin=True)
        if not st.rate('game-rules:'+str(actor['id']),30,60):auth.error('rate_limited',429)
        result=app.state.rpc('/game-rules',data.model_dump())
        st.event('server','game_rule_changed',actor['id'],{key:result[key] for key in ['key','previous','enabled','world']})
        return result
    @app.post('/api/console')
    def console(data:Console,request:Request):
        actor=user(request,admin=True)
        if not st.rate('console:'+str(actor['id']),30,60):auth.error('rate_limited',429)
        result=rpc('/console',{'command':data.command})
        st.event('server','console_command',actor['id'],{'verb':data.command.split(' ')[0][:40]})
        return result

    class ChatMessage(BaseModel):message:str=Field(min_length=1,max_length=500)
    @app.post('/api/chat')
    def chat_message(data:ChatMessage,request:Request):
        actor=user(request,admin=True)
        if not st.rate('chat:'+str(actor['id']),20,60):auth.error('rate_limited',429)
        result=rpc('/console',{'command':'tellraw @a '+json.dumps({'text':data.message},ensure_ascii=False)})
        st.event('server','chat_sent',actor['id'],{'length':len(data.message)})
        return result

    class StoragePreflight(BaseModel):
        kind:str=Field(max_length=30)
        id:str|None=Field(default=None,pattern='^[0-9a-f]{32}$')

    @app.post('/api/storage/preflight')
    def storage_preflight_view(data:StoragePreflight,request:Request):
        user(request,admin=True)
        if data.kind not in storage_preflight.KINDS:auth.error('invalid_storage_operation',409)
        payload={'kind':data.kind}
        if data.kind in {'restore','restore_test'}:
            with st.db() as db:backup=db.execute('SELECT * FROM backups WHERE id=?',(data.id,)).fetchone()
            try:backup_inventory.require_available(Path(os.environ.get('BACKUP_ROOT','/backups')),backup)
            except ValueError:auth.error('backup_unavailable',404)
            payload['archive']=backup['path']
        try:return app.state.rpc('/storage/preflight',payload)
        except (RuntimeError,ValueError,OSError):auth.error('storage_preflight_unavailable',409)

    class Job(BaseModel):
        kind:str=Field(pattern='^(backup|server|mod_check|apply_mods|restore|restore_test|server_settings|version_test|version_apply|source_check|source_stage|mod_version|world_change|world_delete|world_export|curseforge_install)$')
        mode:str=Field(default='manual',pattern='^(manual|idle_now|idle_5min|scheduled|immediate)$')
        payload:dict=Field(default_factory=dict)
        approved:bool=True
        schedule_local:str|None=None
        disconnect_confirmed:bool=False
    @app.post('/api/jobs')
    def jobs_create(data:Job,request:Request):
        actor=user(request,admin=True)
        if data.mode=='immediate' and not data.disconnect_confirmed:auth.error('disconnect_confirmation_required',409)
        if len(json.dumps(data.payload))>16000:auth.error('request_too_large',413)
        if data.kind=='server' and data.payload.get('operation') not in ['start','stop','restart']:auth.error('invalid_operation')
        if data.mode=='scheduled':
            try:data.payload['_scheduled_at']=job_control.berlin_timestamp(data.schedule_local)
            except ValueError as exc:auth.error(str(exc),409)
        if data.kind=='server_settings':
            try:
                allowed={'properties','memory_mb','container_memory_mb'}
                proposed=data.payload.get('changes',{})
                if not isinstance(proposed,dict) or set(proposed)-allowed:raise ValueError('invalid_server_properties')
                current=st.get('server')
                if data.payload.get('basis') is not None and data.payload['basis']!=hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest():raise ValueError('settings_job_stale')
                combined=data.payload.get('include_pending_mods',False)
                if type(combined) is not bool:raise ValueError('invalid_server_properties')
                if combined:
                    reviewed_fingerprint=mods.fingerprint(st)
                    if data.payload.get('mod_fingerprint')!=reviewed_fingerprint:raise ValueError('mod_plan_stale')
                    with st.db() as db:pending=db.execute("SELECT 1 FROM jobs WHERE kind IN ('source_stage','mod_version') AND state IN ('queued','running')").fetchone()
                    if pending or upload_lock.locked():raise ValueError('mod_download_in_progress')
                configuration=server_settings.normalize(current,proposed)
                from . import player_admission
                if player_admission.opens_to_new_players(current,configuration):
                    try:player_admission.require_verified(app.state.rpc('/maintenance-readiness'))
                    except (RuntimeError,httpx.HTTPError):raise ValueError('visitor_admission_requires_verified_guard') from None
                if configuration.get('world')!=current.get('world','world'):raise ValueError('use_world_management')
                if configuration==current:raise ValueError('settings_unchanged')
                schedule={k:v for k,v in data.payload.items() if k=='_scheduled_at'}
                data.payload={'configuration':configuration,'based_on':json.dumps(current,sort_keys=True),**schedule}
                if combined:data.payload.update(include_pending_mods=True,mod_fingerprint=reviewed_fingerprint)
            except (ValueError,TypeError) as exc:auth.error(str(exc),409)
        if data.kind=='curseforge_install':
            project_id=data.payload.get('project_id');file_id=data.payload.get('file_id')
            if type(project_id) is not int or type(file_id) is not int or not 1<=project_id<=2**31-1 or not 1<=file_id<=2**31-1:auth.error('invalid_mod_search_selection',409)
            current=st.get('server');basis={k:current[k] for k in ['version','loader','loader_version']}
            if data.payload.get('basis')!=basis:auth.error('mod_search_runtime_changed',409)
            data.payload={k:v for k,v in data.payload.items() if k in ['project_id','file_id','basis','_scheduled_at']}
        if data.kind in ['world_change','world_delete','world_export']:
            try:
                name=worlds.valid_name(data.payload.get('name',''))
                if data.kind=='world_delete' and name==st.get('server').get('world','world'):raise ValueError('active_world_protected')
                if data.kind=='world_change':
                    generation=data.payload.get('generation',{})
                    if not isinstance(generation,dict) or set(generation)-{'level-seed','level-type','generate-structures','generator-settings'}:raise ValueError('invalid_server_properties')
                    data.payload['configuration']=server_settings.normalize(st.get('server'),{'properties':{'level-name':name,**generation}})
                    data.payload['create']=bool(data.payload.get('create',False))
                data.payload={k:v for k,v in data.payload.items() if k in ['name','configuration','create','_scheduled_at']}
            except ValueError as exc:auth.error(str(exc),409)
        if data.kind in ['source_check','source_stage']:
            try:sources.find_source(st,data.payload.get('id'))
            except ValueError:auth.error('mod_source_unavailable',404)
        if data.kind=='mod_version':
            try:
                identifier=data.payload.get('id');version=data.payload.get('version');pin=data.payload.get('pin',True)
                if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{64}',identifier):raise ValueError('mod_unavailable')
                _,source=mod_versions.record(st,identifier)
                pattern=r'[1-9][0-9]{0,11}' if source['provider']=='curseforge' else r'[A-Za-z0-9]{1,40}'
                if not isinstance(version,str) or not re.fullmatch(pattern,version) or type(pin) is not bool:raise ValueError('invalid_mod_version')
                if data.payload.get('basis')!=mod_versions.basis(st,identifier):raise ValueError('mod_search_runtime_changed')
                schedule={k:v for k,v in data.payload.items() if k=='_scheduled_at'}
                data.payload={'id':identifier,'version':version,'basis':data.payload['basis'],'pin':pin,**schedule}
            except ValueError as exc:auth.error(str(exc),409)
        if data.kind=='apply_mods':
            with st.db() as db:pending=db.execute("SELECT COUNT(*) FROM jobs WHERE kind IN ('source_stage','mod_version') AND state IN ('queued','running')").fetchone()[0]
            if pending or upload_lock.locked():auth.error('mod_download_in_progress',409)
        if data.kind in ['version_test','version_apply'] and not re.fullmatch('[0-9a-f]{32}',str(data.payload.get('id',''))):auth.error('invalid_version_plan',409)
        if data.kind=='restore' and data.payload.get('confirmation')!='restore '+str(data.payload.get('id','')):auth.error('restore_confirmation_required',409)
        if data.kind in ['restore','restore_test'] and not re.fullmatch('[0-9a-f]{32}',str(data.payload.get('id',''))):auth.error('backup_unavailable',404)
        if data.kind in ['restore','restore_test']:
            with st.db() as db:backup=db.execute('SELECT * FROM backups WHERE id=?',(data.payload['id'],)).fetchone()
            try:backup_inventory.require_available(Path(os.environ.get('BACKUP_ROOT','/backups')),backup)
            except ValueError:auth.error('backup_unavailable',404)
        return {'id':add_job(data.kind,data.payload,actor['id'],data.mode,data.approved)}

    @app.get('/api/jobs')
    def jobs_list(request:Request,summary:bool=False):
        actor=user(request)
        with st.db() as db:
            scope="WHERE j.state IN ('planned','queued','running') OR j.id IN (SELECT id FROM jobs WHERE state NOT IN ('planned','queued','running') ORDER BY created DESC LIMIT 3)" if summary else ''
            rows=[dict(x) for x in db.execute("SELECT j.*,u.username AS actor_name FROM jobs j LEFT JOIN users u ON u.id=j.actor "+scope+" ORDER BY CASE WHEN j.state IN ('planned','queued','running') THEN 0 ELSE 1 END,j.created DESC LIMIT 500")]
            identifiers=[json.loads(row['payload']).get('id') for row in rows if row['kind'] in ['version_test','version_apply']]
            plans={x['id']:{'configuration':json.loads(x['configuration']),'based_on':json.loads(x['based_on'])} for x in db.execute('SELECT id,configuration,based_on FROM version_plans WHERE id IN ('+','.join('?' for _ in identifiers)+')',identifiers)} if identifiers else {}
        current=st.get('server')
        for row in rows:
            payload=json.loads(row['payload'])
            if row['kind'] in ['version_test','version_apply']:
                plan=plans.get(payload.get('id'),{'configuration':current,'based_on':current});row['purpose']=job_control.purpose(plan['based_on'],plan['configuration'])
            if row['kind']=='server':row['operation']=payload.get('operation')
            if row['kind']=='server_settings':row['combined_changes']=payload.get('include_pending_mods',False);row['protection_update']=payload.get('protection_update',False)
            if summary:
                result=json.loads(row['result'] or '{}')
                row['payload']=json.dumps({k:v for k,v in payload.items() if k in ['id','name','operation','_scheduled_at']})
                brief={k:v for k,v in result.items() if k in ['started','progress','reason']}
                report=result.get('dependency_report')
                issues=report.get('issues',[]) if isinstance(report,dict) else []
                if isinstance(issues,list) and issues:
                    brief['dependency_report']={'issues':[{k:str(v)[:500] for k,v in issue.items() if k in ['filename','id','issue','dependency','required','actual']} for issue in issues[:5] if isinstance(issue,dict)]}
                row['result']=json.dumps(brief)
        if not actor['admin']:
            from .public_views import job as public_job
            rows=[public_job(row) for row in rows]
        return rows

    @app.post('/api/jobs/{identifier}/approve')
    def job_approve(identifier:str,request:Request):
        actor=user(request,admin=True)
        with st.db() as db:
            changed=db.execute("UPDATE jobs SET state='queued',approved=1,actor=?,mode='idle_now',updated=? WHERE id=? AND state='planned'",(actor['id'],time.time(),identifier))
            if changed.rowcount!=1:auth.error('job_not_approvable',409)
        st.event('maintenance','job_approved',actor['id'],{'id':identifier});return {'state':'queued'}

    class RunNow(BaseModel):confirmation:str=Field(pattern='^run_now$')

    @app.post('/api/jobs/{identifier}/run-now')
    def job_run_now(identifier:str,data:RunNow,request:Request):
        actor=user(request,admin=True)
        with st.db(immediate=True) as db:
            row=db.execute("SELECT * FROM jobs WHERE id=? AND state IN ('planned','queued')",(identifier,)).fetchone()
            if not row or row['mode']=='immediate':auth.error('job_not_forceable',409)
            if db.execute("SELECT 1 FROM jobs WHERE state='running'").fetchone():auth.error('maintenance_busy',409)
            payload=json.loads(row['payload']);payload.pop('_scheduled_at',None)
            if payload.get('automatic'):payload['automatic']=False
            db.execute("UPDATE jobs SET state='queued',approved=1,actor=?,mode='immediate',payload=?,updated=? WHERE id=?",(actor['id'],json.dumps(payload),time.time(),identifier))
            db.execute("INSERT INTO events(at,category,event,actor,data) VALUES(?,?,?,?,?)",(time.time(),'maintenance','job_run_now_requested',actor['id'],json.dumps({'id':identifier,'previous_mode':row['mode']})))
        return {'state':'queued','mode':'immediate','id':identifier}

    @app.post('/api/jobs/{identifier}/cancel')
    def job_cancel(identifier:str,request:Request):
        actor=user(request,admin=True)
        with st.db() as db:
            changed=db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=? AND state IN ('planned','queued')",(time.time(),identifier))
            if changed.rowcount!=1:auth.error('job_not_cancellable',409)
        st.event('maintenance','job_cancelled',actor['id'],{'id':identifier});return {'state':'cancelled'}

    @app.get('/api/mods')
    def mods_list(request:Request):
        user(request)
        with st.db() as db:records=[dict(x) for x in db.execute("SELECT * FROM mods WHERE state!='superseded' ORDER BY filename")]
        for record in records:
            record['metadata']=json.loads(record['metadata']);record['available']=json.loads(record['available']) if record['available'] else {'status':'not_checked'}
            record['protected']=record['source']=='system'
            if record['protected']:
                record['available']={'status':'system_managed','version':record['metadata']['mods'][0]['version']}
            origin=json.loads(record['origin']) if record.get('origin') else {}
            if origin.get('provider')=='manual_patch':
                record['locally_patched']=True
                record['available']={'status':'locally_patched','version':record['metadata']['mods'][0]['version']}
                try:
                    upstream=sources.reference(origin.get('url',''))
                    if upstream['provider']=='curseforge' and upstream['kind']=='mod':record['upstream_url']=upstream['url']
                except ValueError:pass
        replacements={row.get('replaces'):row for row in records if row['state']=='staged' and row.get('replaces')}
        for row in records:
            replacement=replacements.get(row['id'])
            if replacement:
                row['pending_update']={'id':replacement['id'],'filename':replacement['filename'],'versions':replacement['metadata']['mods']}
                origin=json.loads(replacement['origin']) if replacement.get('origin') else {}
                available=row['available']
                if origin.get('file_id') is not None and origin['file_id'] in [available.get('curseforge_file_id'),available.get('modrinth_version_id')]:
                    row['available']={**available,'status':'update_prepared'}
        server=versions.runtime_components(st,st.get('server'))
        return {'mods':records,'fingerprint':mods.fingerprint(st),'loader_components':server.get('loader_components'),'dependencies':mods.dependency_report([x for x in mods.proposed_records(records) if x['enabled']],server)}

    class ModDesired(BaseModel):enabled:bool
    @app.get('/api/mods/test-results')
    def mod_test_results(request:Request):
        user(request)
        try:return {'report':mods.trial_report(st)}
        except (ValueError,OSError):auth.error('mod_test_report_invalid',409)

    @app.post('/api/mods/{identifier}/desired')
    def mod_desired(identifier:str,data:ModDesired,request:Request):
        actor=user(request,admin=True)
        with st.change_lock(),st.db() as db:
            record=db.execute('SELECT * FROM mods WHERE id=?',(identifier,)).fetchone()
            if not record:auth.error('mod_unavailable',404)
            if record['source']=='system':auth.error('visitor_guard_is_protected',409)
            if record['remove_pending'] is not None:auth.error('mod_removal_pending',409)
            if data.enabled and json.loads(record['metadata']).get('client_installer'):auth.error('client_installer_not_server_mod',409)
            db.execute('UPDATE mods SET enabled=?,updated=? WHERE id=?',(int(data.enabled),time.time(),identifier))
        st.event('mods','mod_desired_changed',actor['id'],{'id':identifier,'enabled':data.enabled})
        return {'state':'planned','enabled':data.enabled,'installed':False}

    class ModRemoval(BaseModel):remove:bool=True

    @app.post('/api/mods/{identifier}/removal')
    def mod_removal(identifier:str,data:ModRemoval,request:Request):
        actor=user(request,admin=True)
        with st.change_lock(),st.db(immediate=True) as db:
            record=db.execute("SELECT * FROM mods WHERE id=? AND state NOT IN ('superseded','rejected')",(identifier,)).fetchone()
            if not record:auth.error('mod_unavailable',404)
            if record['source']=='system':auth.error('visitor_guard_is_protected',409)
            if data.remove:
                if db.execute("SELECT 1 FROM mods WHERE replaces=? AND state='staged'",(identifier,)).fetchone():auth.error('mod_update_pending',409)
                db.execute('UPDATE mods SET remove_pending=COALESCE(remove_pending,enabled),enabled=0,updated=? WHERE id=?',(time.time(),identifier))
            elif record['remove_pending'] is not None:
                db.execute('UPDATE mods SET enabled=remove_pending,remove_pending=NULL,updated=? WHERE id=?',(time.time(),identifier))
        st.event('mods','mod_removal_staged' if data.remove else 'mod_removal_cancelled',actor['id'],{'id':identifier})
        return {'state':'planned','installed':False,'removal_pending':data.remove}

    @app.get('/api/mods/{identifier}/versions')
    def mod_version_catalog(identifier:str,request:Request,offset:int=0):
        actor=user(request,admin=True)
        if not st.rate('mod-versions:'+str(actor['id']),15,60):auth.error('rate_limited',429)
        try:return mod_versions.catalog(st,identifier,offset)
        except ValueError as exc:auth.error(str(exc),409)

    @app.post('/api/mods/{identifier}/update/cancel')
    def cancel_mod_update(identifier:str,request:Request):
        actor=user(request,admin=True)
        with st.change_lock(),st.db(immediate=True) as db:
            row=db.execute("SELECT * FROM mods WHERE id=? AND state='installed'",(identifier,)).fetchone()
            if not row:auth.error('mod_unavailable',404)
            if row['source']=='system':auth.error('visitor_guard_is_protected',409)
            if db.execute("SELECT 1 FROM jobs WHERE kind IN ('source_stage','mod_version','curseforge_install') AND state IN ('queued','running')").fetchone():auth.error('mod_download_in_progress',409)
            changed=db.execute("UPDATE mods SET state='superseded',enabled=0,updated=? WHERE replaces=? AND state='staged' AND installed_enabled=0",(time.time(),identifier)).rowcount
        st.event('mods','mod_update_cancelled',actor['id'],{'id':identifier,'count':changed})
        return {'cancelled':changed,'live_server_changed':False}

    @app.post('/api/mods/upload')
    async def mods_upload(request:Request,files:list[UploadFile]=File(...)):
        actor=user(request,admin=True)
        if len(files)>20:auth.error('too_many_files')
        result=[]
        for file in files:
            raw=await file.read(mods.MAX_JAR+1)
            try:record=mods.stage(st,root,raw,file.filename or '')
            except ValueError as exc:auth.error(str(exc))
            result.append(record);st.event('mods','jar_staged',actor['id'],{'id':record['id'],'filename':record['filename']})
        return {'staged':result,'installed':False}

    @app.post('/api/mods/{identifier}/update')
    def mod_update(identifier:str,request:Request):
        actor=user(request,admin=True)
        if not st.rate('mod-download:'+str(actor['id']),4,60):auth.error('rate_limited',429)
        try:return sources.stage_update(st,root,identifier)
        except ValueError as exc:auth.error(str(exc),409)
        except httpx.HTTPError:auth.error('mod_provider_unavailable',503)

    @app.get('/api/mods/curseforge/search')
    def curseforge_search(request:Request,query:str,offset:int=0):
        actor=user(request,admin=True)
        if not st.rate('curseforge-search:'+str(actor['id']),12,60):auth.error('rate_limited',429)
        try:return sources.search_curseforge(st,query,offset)
        except ValueError as exc:auth.error(str(exc),409)
        except httpx.HTTPError:auth.error('mod_provider_unavailable',503)

    @app.get('/api/mods/sources')
    def source_list(request:Request):
        user(request)
        return {'sources':sources.inventory(st),'pending_packs':st.get('pack_pending') or []}

    class SourceList(BaseModel):sources:list=Field(max_length=100)
    @app.post('/api/mods/sources')
    def source_save(data:SourceList,request:Request):
        actor=user(request,admin=True)
        try:result=sources.save_list(st,data.sources)
        except ValueError as exc:auth.error(str(exc))
        st.event('mods','source_list_updated',actor['id'],{'count':len(result)})
        return {'sources':result}

    class PackProperties(BaseModel):enabled:bool
    @app.post('/api/mods/packs/{identifier}/properties')
    def pack_properties(identifier:str,data:PackProperties,request:Request):
        actor=user(request,admin=True)
        with st.change_lock():
            pending=st.get('pack_pending') or [];matches=[x for x in pending if x['id']==identifier]
            if len(matches)!=1:auth.error('pack_plan_unavailable',404)
            matches[0]['apply_properties']=data.enabled;st.set('pack_pending',pending)
        st.event('mods','pack_properties_selected',actor['id'],{'id':identifier,'enabled':data.enabled})
        return {'ok':True}

    async def receive_archive(request,maximum):
        target=project_path(root,'staging')/('upload-'+secrets.token_hex(16)+'.zip')
        target.parent.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(target.parent).free<maximum+20*1024**3:auth.error('insufficient_import_space',409)
        total=0
        try:
            with target.open('xb') as stream:
                os.chmod(target,0o600)
                async for chunk in request.stream():
                    total+=len(chunk)
                    if total>maximum:auth.error('request_too_large',413)
                    stream.write(chunk)
                stream.flush();os.fsync(stream.fileno())
            if not total:auth.error('pack_manifest_invalid')
            return target
        except BaseException:
            if target.exists():target.unlink()
            raise

    @app.get('/api/worlds')
    def worlds_list(request:Request):
        user(request,admin=True)
        value=rpc('/worlds')
        exports=[]
        for path in (st.state/'world-exports').glob('*.json'):
            if not path.is_symlink() and path.stat().st_size<4096:
                try:exports.append(json.loads(path.read_text()))
                except ValueError:pass
        return {**value,'imports':st.get('world_imports') or [],'current':st.get('server').get('world','world'),'exports':sorted(exports,key=lambda x:x['created'],reverse=True)[:30]}

    @app.get('/api/worlds/exports/{identifier}/download')
    def world_export_download(identifier:str,request:Request):
        user(request,admin=True)
        if not re.fullmatch('[0-9a-f]{32}',identifier):auth.error('world_unavailable',404)
        path=st.state/'world-exports'/(identifier+'.zip')
        if path.is_symlink() or not path.is_file():auth.error('world_unavailable',404)
        return FileResponse(path,media_type='application/zip',filename='Minecraft-world-'+identifier+'.zip')

    @app.post('/api/worlds/upload')
    async def world_upload(request:Request,name:str):
        actor=user(request,admin=True)
        try:worlds.valid_name(name)
        except ValueError as exc:auth.error(str(exc),409)
        existing=rpc('/worlds')['worlds']
        if any(x['name']==name for x in existing):auth.error('world_name_already_exists',409)
        path=await receive_archive(request,worlds.MAX_ARCHIVE)
        try:
            result=await asyncio.to_thread(worlds.stage,st,root,path,name)
            st.event('server','world_import_staged',actor['id'],{'name':name,'id':result['id'],'files':result['files']})
            return result
        except ValueError as exc:auth.error(str(exc),409)
        finally:
            if path.exists():path.unlink()

    @app.post('/api/packs/upload')
    async def pack_upload(request:Request,source_id:str|None=None,allow_prerelease:bool=False):
        actor=user(request,admin=True)
        if source_id and not re.fullmatch('[0-9a-f]{24}',source_id):auth.error('mod_source_unavailable',404)
        path=await receive_archive(request,packs.MAX_ARCHIVE)
        try:
            result=await asyncio.to_thread(packs.stage_uploaded,st,root,path,source_id,allow_prerelease)
            st.event('mods','pack_staged',actor['id'],{'id':result['pending_pack']['id'],'files':len(result['staged'])})
            return result
        except ValueError as exc:auth.error(str(exc),409)
        except httpx.HTTPError:auth.error('mod_provider_unavailable',503)
        finally:
            if path.exists():path.unlink()

    @app.get('/api/mods/export')
    def mods_export(request:Request):
        user(request)
        with st.db() as db:records=[{'filename':x['filename'],'sha256':x['sha256'],'enabled':bool(x['enabled']),
                       'state':x['state'],'metadata':json.loads(x['metadata'])} for x in db.execute('SELECT * FROM mods')]
        return JSONResponse({'format':'mcj-client-mod-list-1','server':client_packs.runtime(st.get('server')),'mods':records,
                             'redistributed_jars':False},headers={'Content-Disposition':'attachment; filename="minecraft-modlist.json"'})

    @app.get('/api/client-packs')
    def client_pack_list(request:Request):
        user(request,admin=True)
        result=client_packs.listing(st)
        snapshot=app.state.rpc('/client-pack/snapshot')
        observed=snapshot['fingerprint']
        result['basis']=observed
        result['mod_sides']=[{'sha256':r['hashes']['sha256'],'filename':r['filename'],'mods':r['metadata']['mods'],
            'locked':client_packs.server_only(r),'side':snapshot.get('client_sides',{}).get(r['hashes']['sha256'],'auto')}
            for r in snapshot.get('mods',[])]
        current_id=next((pack['id'] for pack in result['packs'] if pack['fingerprint']==observed),None)
        for pack in result['packs']:
            pack['current']=pack['id']==current_id
            pack['matches_current']=pack['fingerprint']==observed
            if pack['fingerprint']!=observed:pack['active_links']=0
        for link in result['links']:link['current']=link.pop('fingerprint')==observed
        return result

    @app.get('/api/client-packs/catalog')
    def client_pack_catalog(request:Request,before:int|None=None):
        user(request,admin=True)
        try:return client_pack_compare.catalog(st,before)
        except (ValueError,TypeError,KeyError) as exc:auth.error('client_pack_invalid_page' if str(exc)=='client_pack_invalid_page' else 'client_pack_manifest_invalid',422 if str(exc)=='client_pack_invalid_page' else 409)

    @app.get('/api/client-packs/compare')
    def compare_client_packs(request:Request,before:str,after:str):
        user(request,admin=True)
        try:return client_pack_compare.compare(st,before,after)
        except (ValueError,TypeError,OSError,KeyError,zipfile.BadZipFile) as exc:auth.error(str(exc) if isinstance(exc,ValueError) and str(exc).startswith('client_pack_') else 'client_pack_integrity_failed',409)

    @app.post('/api/client-packs/build')
    def client_pack_build(request:Request):
        actor=user(request,admin=True)
        if not st.rate('client-pack-build',2,60):auth.error('rate_limited',429)
        with st.db() as db:
            if db.execute("SELECT 1 FROM jobs WHERE kind='client_pack_build' AND state IN ('queued','running')").fetchone():auth.error('maintenance_busy',409)
        return {'id':add_job('client_pack_build',{},actor['id'])}

    class ClientSideSelection(BaseModel):
        sha256:str=Field(pattern='^[0-9a-f]{64}$')
        side:Literal['auto','required','optional','unsupported']
        basis:str=Field(pattern='^[0-9a-f]{64}$')

    @app.post('/api/client-packs/side')
    def client_side_selection(data:ClientSideSelection,request:Request):
        actor=user(request,admin=True)
        try:return app.state.rpc('/client-pack/side',{**data.model_dump(),'actor':actor['id']})
        except (ValueError,RuntimeError) as exc:auth.error(str(exc),409)

    @app.get('/api/client-packs/{identifier}/download')
    def client_pack_download(request:Request,identifier:str):
        user(request,admin=True)
        try:path,row=client_packs.archive(st,identifier)
        except (ValueError,OSError):auth.error('client_pack_not_found',404)
        return FileResponse(path,media_type='application/x-modrinth-modpack+zip',filename='MCJ-'+json.loads(row['manifest'])['version']+'.mrpack')

    class ClientShare(BaseModel):
        days:int|None=Field(default=7,ge=1,le=30,strict=True)

    @app.post('/api/client-packs/{identifier}/share')
    def client_pack_share(request:Request,identifier:str,data:ClientShare):
        actor=user(request,admin=True)
        if not st.rate('client-pack-share:'+str(actor['id']),12,60):auth.error('rate_limited',429)
        try:
            _,row=client_packs.archive(st,identifier)
            if row['fingerprint']!=app.state.rpc('/client-pack/snapshot')['fingerprint']:auth.error('client_pack_outdated',409)
            result=client_packs.share(st,identifier,actor['id'],data.days)
        except (ValueError,OSError):auth.error('client_pack_not_found',404)
        result['url']=canonical_origin()+'/client-pack#'+result.pop('token')
        return result

    @app.post('/api/client-packs/links/{identifier}/revoke')
    def client_pack_revoke(request:Request,identifier:str):
        actor=user(request,admin=True)
        with st.db() as db:
            count=db.execute('UPDATE client_pack_links SET revoked=? WHERE id=? AND revoked IS NULL',(time.time(),identifier)).rowcount
        if count:st.event('mods','client_pack_link_revoked',actor['id'],{'id':identifier})
        return {'revoked':True}

    class ClientCapability(BaseModel):
        token:str=Field(min_length=43,max_length=43,pattern='^[A-Za-z0-9_-]+$')

    def shared_pack(request,token):
        if not st.rate('client-pack-public:'+auth.client_address(request),60,60):auth.error('rate_limited',429)
        try:
            row=client_packs.authorize_share(st,token,None)
            if row['fingerprint']!=app.state.rpc('/client-pack/snapshot')['fingerprint']:raise ValueError('client_pack_outdated')
            return row
        except ValueError as exc:auth.error('client_pack_outdated' if str(exc)=='client_pack_outdated' else 'client_pack_link_invalid',409 if str(exc)=='client_pack_outdated' else 404)
        except RuntimeError:auth.error('client_pack_temporarily_unavailable',503)

    @app.post('/client-pack/info')
    def shared_pack_info(request:Request,data:ClientCapability):
        row=shared_pack(request,data.token);value=json.loads(row['manifest'])
        return {'version':value['version'],'runtime':value['runtime'],'expires':row['expires'],
                'mods':[{'name':', '.join(x['name'] for x in m['mods']),'version':', '.join(x['version'] for x in m['mods'])} for m in value['mods'] if m['client'] in ['required','optional']],
                'graphics':[{'name':x['path'].split('/')[-1],'version':x['version'],'evidence':x['evidence']} for x in (value.get('graphics') or {}).get('files',[])],
                'create_iris_patch':bool((value.get('graphics') or {}).get('create_compatibility_patch')),
                'excluded_unknown':sum(m['client']=='unknown' for m in value['mods'])}

    @app.post('/client-pack/download')
    async def shared_pack_download(request:Request):
        from urllib.parse import parse_qs
        form=parse_qs((await request.body()).decode('ascii',errors='replace'),max_num_fields=2)
        values=form.get('token',[])
        if len(values)!=1:auth.error('client_pack_link_invalid',404)
        row=shared_pack(request,values[0])
        try:path,pack=client_packs.archive(st,row['pack_id'])
        except (ValueError,OSError):auth.error('client_pack_not_found',404)
        return FileResponse(path,media_type='application/x-modrinth-modpack+zip',filename='MCJ-'+json.loads(pack['manifest'])['version']+'.mrpack')

    @app.get('/client-pack')
    @app.get('/client-pack/{asset}')
    def client_pack_landing(asset:str=''):
        mapping={'':'client-pack.html','app.js':'client-pack.js','style.css':'client-pack.css','icon.svg':'favicon.svg'}
        if asset not in mapping:auth.error('not_found',404)
        return FileResponse(Path(__file__).parent/'static'/mapping[asset])

    class DeleteItems(BaseModel):
        ids:list[str]=Field(min_length=1,max_length=100)
        confirmation:str|None=Field(default=None,max_length=64)

    @app.post('/api/backups/delete')
    def delete_backups(data:DeleteItems,request:Request):
        actor=user(request,admin=True)
        try:return rpc('/backup/delete',{**data.model_dump(),'actor':actor['id']})
        except (ValueError,RuntimeError) as exc:auth.error(str(exc),409)

    @app.post('/api/client-packs/delete')
    def delete_client_packs(data:DeleteItems,request:Request):
        actor=user(request,admin=True)
        try:
            return app.state.rpc('/client-pack/delete',{**data.model_dump(),'actor':actor['id']})
        except (ValueError,RuntimeError,OSError) as exc:auth.error(str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'delete_item_unavailable',409)

    @app.get('/api/backups')
    def backups(request:Request):
        user(request)
        with st.db() as db:rows=[dict(x) for x in db.execute('SELECT * FROM backups ORDER BY created DESC,id DESC LIMIT 2000')]
        return [{**row,**backup_inventory.archive_info(Path(os.environ.get('BACKUP_ROOT','/backups')),row)} for row in rows]

    @app.get('/api/backups/schedule')
    def backups_schedule(request:Request):
        user(request,admin=True)
        from .backup_schedule import status
        try:server=rpc('/status')
        except Exception:server={}
        return status(st,server,backup_root=Path(os.environ.get('BACKUP_ROOT','/backups')))

    @app.get('/api/backups/history')
    def backup_history(request:Request,limit:int=100,cursor:str='',state:str='',kind:str='',after:float=0,before:float=0):
        user(request)
        try:
            backup_root=Path(os.environ.get('BACKUP_ROOT','/backups'))
            result=backup_inventory.page(st,backup_root,limit=limit,cursor=cursor,state=state,kind=kind,after=after,before=before)
            try:
                protection=app.state.rpc('/backup/protection')
                identifiers=protection['protected_ids']
                if not isinstance(identifiers,list) or any(not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value) for value in identifiers):
                    raise ValueError('invalid_backup_protection')
                protected=set(identifiers)
            except (RuntimeError,ValueError,KeyError,TypeError,httpx.HTTPError):
                auth.error('backup_protection_unavailable',503)
            for record in result['records']:record['protected']=record['id'] in protected
            return result
        except ValueError as exc:auth.error(str(exc),400)

    @app.get('/api/backups/{identifier}/download')
    def backup_download(identifier:str,request:Request):
        user(request,admin=True)
        with st.db() as db:row=db.execute('SELECT * FROM backups WHERE id=?',(identifier,)).fetchone()
        try:backup_inventory.require_available(Path(os.environ.get('BACKUP_ROOT','/backups')),row)
        except ValueError:auth.error('backup_unavailable',404)
        name=row['path']
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.tar\.gz',name):auth.error('backup_path_invalid',409)
        path=Path(os.environ.get('BACKUP_ROOT','/backups'))/name
        if not path.is_file() or path.is_symlink():auth.error('backup_unavailable',404)
        return FileResponse(path,media_type='application/gzip',filename=name)

    @app.get('/api/events')
    def events(request:Request,category:str='',after:int=0):
        actor=user(request,admin=True)
        with st.db() as db:
            rows=db.execute('SELECT * FROM events WHERE id>? AND (?=\'\' OR category=?) ORDER BY id DESC LIMIT 1000',(after,category,category))
            result=[{**dict(x),'data':json.loads(x['data'])} for x in rows]
        for item in result:
            item['title'],item['description']=dispatch.notification_text.describe(item,actor['language'],dispatch.LABELS,st)
        return result

    @app.get('/api/events/export')
    def events_export(request:Request):
        user(request,admin=True)
        out=io.StringIO();writer=csv.writer(out);writer.writerow(['id','utc_epoch','category','event','actor','data'])
        with st.db() as db:
            for row in db.execute('SELECT * FROM events ORDER BY id'):
                values=[row[x] for x in ['id','at','category','event','actor','data']]
                writer.writerow([("'"+str(x)) if str(x).startswith(('=','+','-','@')) else x for x in values])
        return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="events.csv"'})

    from . import event_history

    @app.get('/api/events/cleanup-policy')
    def event_cleanup_policy(request:Request):
        user(request,admin=True)
        return {'policy':event_history.policy(st),'last':st.get('event_cleanup_last')}

    @app.post('/api/events/cleanup-policy')
    def save_event_cleanup_policy(data:event_history.Policy,request:Request):
        actor=user(request,admin=True);now=time.time();value=data.model_dump()
        with st.db(immediate=True) as db:
            values={'event_cleanup':value,'event_cleanup_approval':{'actor':actor['id'],'generation':actor['generation'],'at':now} if value['enabled'] else None,'event_cleanup_last':{'at':now,'events_deleted':0,'deliveries_deleted':0}}
            for key,val in values.items():db.execute('INSERT INTO settings VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',(key,json.dumps(val)))
        st.event('audit','event_cleanup_policy_updated',actor['id'],value)
        return {'policy':value}

    @app.post('/api/events/cleanup-preview')
    def event_cleanup_preview(data:event_history.Preview,request:Request):
        actor=user(request,admin=True)
        if not st.rate('event-cleanup-preview:'+str(actor['id']),10,60):auth.error('rate_limited',429)
        try:return event_history.preview(st,actor,data)
        except ValueError as exc:auth.error(str(exc))

    @app.post('/api/events/cleanup')
    def event_cleanup(data:event_history.Delete,request:Request):
        actor=user(request,admin=True)
        try:return event_history.delete(st,actor,data.token)
        except ValueError as exc:auth.error(str(exc),409)

    @app.get('/api/settings')
    def settings(request:Request):
        user(request,admin=True)
        smtp=st.get('smtp');smtp['password_configured']=bool(smtp.pop('password',''))
        discord=st.get('discord');discord['webhook_configured']=bool(discord.pop('webhook',''))
        providers=st.get('providers');providers['curseforge_api_key_configured']=bool(providers.pop('curseforge_api_key',''))
        from . import application_update
        return {'server':st.get('server'),'maintenance':st.get('maintenance'),'greetings':st.get('greetings'),'smtp':smtp,'discord':discord,'providers':providers,'application_update':application_update.status(st),
                'release':st.get('release'),'infrastructure':{'web_host_port':8090,'web_binding':'127.0.0.1',
                    'game_published':bool(st.get('release').get('public_game')),'reverse_proxy':'externally_managed'}}

    @app.get('/api/player-admission')
    def player_admission_status(request:Request):
        user(request,admin=True)
        from .player_admission import view
        try:
            properties=app.state.rpc('/properties');ready=app.state.rpc('/maintenance-readiness')
        except (RuntimeError,httpx.HTTPError):auth.error('player_admission_unavailable',409)
        return view(st.get('server'),properties,ready)

    @app.get('/api/application-update/template')
    def application_update_template(request:Request):
        user(request,admin=True)
        from .application_update import template
        return Response(template(),media_type='application/yaml',headers={'Content-Disposition':'attachment; filename="mcj-aktualisierung.yaml"'})

    @app.get('/api/infrastructure/web')
    def infrastructure_web(request:Request):
        user(request,admin=True)
        proxies,networks=connection_policy()
        return {**web_access.settings(st,origin),'local_connection':request.state.local_connection,
                'proxy_configured':bool(proxies),'local_network_configured':bool(networks)}

    @app.get('/api/infrastructure/connections')
    def infrastructure_connections(request:Request):
        user(request,admin=True);proxies,networks=connection_policy()
        return {'proxies':','.join(sorted(proxies)),'networks':','.join(map(str,networks)),
                'peer':request.client.host if request.client else '', 'local_connection':request.state.local_connection}

    class ConnectionPolicy(BaseModel):
        proxies:str=Field(default='',max_length=500)
        networks:str=Field(default='',max_length=500)
        confirmed:StrictBool=False
    @app.post('/api/infrastructure/connections')
    def infrastructure_connections_change(data:ConnectionPolicy,request:Request):
        actor=user(request,admin=True)
        if not request.state.local_connection or not data.confirmed:auth.error('web_access_requires_local_connection',409)
        if not st.rate('connection-policy:'+str(actor['id']),5,3600):auth.error('rate_limited',429)
        try:
            proxies=web_access.configured_proxies(data.proxies);networks=web_access.configured_local_networks(data.networks)
            # Test the exact current connection against the proposed policy before saving.
            address,local=web_access.incoming(request,proxies,networks)
            if address is None or not local:raise ValueError('connection_policy_would_lock_out')
        except ValueError as exc:auth.error(str(exc),409)
        with st.change_lock():st.set('connection_policy',{'proxies':','.join(sorted(proxies)),'networks':','.join(map(str,networks))})
        st.event('settings','connection_policy_changed',actor['id'],{})
        return {'saved':True,'minecraft_restart_required':False}

    @app.get('/api/infrastructure/tls')
    def infrastructure_tls(request:Request):
        user(request,admin=True)
        if os.environ.get('MCJ_TLS_MODE')!='selfsigned':return {'mode':'proxy','managed':False}
        from . import local_tls
        try:return local_tls.status(Path(os.environ.get('MCJ_TLS_DIR','/run/mcj-tls')))
        except (OSError,ValueError):auth.error('tls_unavailable',503)

    @app.get('/api/infrastructure/tls/authority')
    def infrastructure_tls_authority(request:Request):
        user(request,admin=True)
        if os.environ.get('MCJ_TLS_MODE')!='selfsigned':auth.error('tls_not_managed',409)
        from . import local_tls
        base=Path(os.environ.get('MCJ_TLS_DIR','/run/mcj-tls'))
        try:
            local_tls.status(base)
            return Response(local_tls._safe_file(base/'authority.crt'),media_type='application/x-x509-ca-cert',headers={'Content-Disposition':'attachment; filename="Minecraft-Java-Manager-Heimnetz.crt"','Cache-Control':'no-store'})
        except (OSError,ValueError):auth.error('tls_unavailable',503)

    class TLSRenew(BaseModel):confirmed:StrictBool=False
    @app.post('/api/infrastructure/tls/renew')
    def infrastructure_tls_renew(data:TLSRenew,request:Request):
        actor=user(request,admin=True)
        if not data.confirmed:auth.error('tls_confirmation_required',409)
        if os.environ.get('MCJ_TLS_MODE')!='selfsigned' or not getattr(app.state,'tls_reload',None):auth.error('tls_not_managed',409)
        if not st.rate('tls-renew:'+str(actor['id']),3,3600):auth.error('rate_limited',429)
        from . import local_tls
        try:
            with st.change_lock():result=local_tls.renew(Path(os.environ.get('MCJ_TLS_DIR','/run/mcj-tls')),app.state.tls_reload)
        except (OSError,ValueError):auth.error('tls_unavailable',503)
        st.event('settings','tls_certificate_renewed',actor['id'],{'expires':result['expires'],'fingerprint':result['fingerprint']})
        return {**result,'minecraft_restart_required':False}

    class WebAccessChange(BaseModel):
        address:str
        external_web:StrictBool
        basis:str
        confirmation:str=''
    @app.post('/api/infrastructure/web')
    def infrastructure_web_change(data:WebAccessChange,request:Request):
        actor=user(request,admin=True)
        if not st.rate('web-access:'+str(actor['id']),10,60):auth.error('rate_limited',429)
        proxies,networks=connection_policy()
        try:return web_access.change(st,origin,actor,data.model_dump(),data.basis,data.confirmation,
                                    request.state.local_connection,bool(proxies or networks))
        except ValueError as exc:auth.error(str(exc),409)

    class WebAccessActivate(BaseModel):basis:str
    @app.post('/api/infrastructure/web/activate')
    def infrastructure_web_activate(data:WebAccessActivate,request:Request):
        actor=user(request,admin=True)
        try:
            result=web_access.activate(st,origin,actor,request.state.request_origin,data.basis)
            app.state.origin=result['address'];return result
        except ValueError as exc:auth.error(str(exc),409)

    @app.get('/api/infrastructure/game')
    def infrastructure_game(request:Request):
        user(request,admin=True)
        try:return app.state.rpc('/network-access')
        except (RuntimeError,httpx.HTTPError):return {'public_game':None,'ready':False,'reason':'game_access_unavailable'}

    class GameProtectionUpdate(BaseModel):basis:str
    @app.post('/api/infrastructure/game/update')
    def infrastructure_game_update(data:GameProtectionUpdate,request:Request):
        actor=user(request,admin=True)
        if not st.rate('protection-update:'+str(actor['id']),5,3600):auth.error('rate_limited',429)
        try:available=app.state.rpc('/network-access')
        except (RuntimeError,httpx.HTTPError):auth.error('game_access_unavailable',409)
        if not available.get('update_available') or data.basis!=available.get('update_basis'):auth.error('protection_update_changed',409)
        current=st.get('server')
        identifier=add_job('server_settings',{'configuration':current,'based_on':json.dumps(current,sort_keys=True),
                           'protection_update':True,'guard_sha256':available['update_guard_sha256']},actor['id'],mode='idle_5min')
        return {'id':identifier,'mode':'idle_5min','pending_mods_included':False}

    class GameAccessChange(BaseModel):
        public_game:StrictBool
        basis:str
        confirmed:StrictBool=False
    @app.post('/api/infrastructure/game')
    def infrastructure_game_change(data:GameAccessChange,request:Request):
        actor=user(request,admin=True)
        if not data.confirmed:auth.error('game_access_confirmation_required',409)
        if not st.rate('game-access:'+str(actor['id']),10,60):auth.error('rate_limited',429)
        try:result=app.state.rpc('/network-access',{'public_game':data.public_game,'basis':data.basis})
        except (RuntimeError,httpx.HTTPError) as exc:auth.error(str(exc) if isinstance(exc,RuntimeError) else 'game_access_unavailable',409)
        st.event('system','game_access_changed',actor['id'],{'public_game':data.public_game})
        return result

    class Settings(BaseModel):section:str=Field(pattern='^(smtp|discord|maintenance|providers|greetings)$');value:dict
    @app.post('/api/settings')
    def save_settings(data:Settings,request:Request):
        actor=user(request,admin=True)
        value=data.value;old=st.get(data.section)
        if data.section=='greetings':
            from . import greetings
            try:value=greetings.validate(value)
            except ValueError:auth.error('invalid_greeting_settings')
            st.set('greetings',value)
        elif data.section=='providers':
            if set(value)-{'curseforge_api_key'}:auth.error('invalid_setting')
            key=value.get('curseforge_api_key') or old.get('curseforge_api_key','')
            if not isinstance(key,str) or len(key)>1000 or '\r' in key or '\n' in key:auth.error('invalid_api_key')
            st.set('providers',{'curseforge_api_key':key},True)
        elif data.section=='smtp':
            if set(value)-{'host','port','security','username','sender','password'}:auth.error('invalid_setting')
            if value.get('security') not in ['tls','starttls']:auth.error('encrypted_smtp_required')
            if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}',str(value.get('host',''))):auth.error('invalid_smtp_host')
            if not isinstance(value.get('port'),int) or not 1<=value['port']<=65535:auth.error('invalid_port')
            for key in ['username','sender']:
                if not re.fullmatch(r'[^\s@\r\n]{1,120}@[^\s@\r\n]{1,120}',str(value.get(key,''))):auth.error('invalid_email')
            if not value.get('password'):
                if value['host']!=old['host'] or value['username']!=old['username']:auth.error('new_password_required_for_new_smtp_destination')
                value['password']=old['password']
            if len(value['password'])>1000:auth.error('invalid_password')
            st.set('smtp',value,True)
        elif data.section=='discord':
            if set(value)-{'enabled','webhook','events','language'}:auth.error('invalid_setting')
            webhook=value.get('webhook') or old['webhook']
            if webhook:
                try:discord_url(webhook)
                except ValueError:auth.error('invalid_discord_webhook')
            if not isinstance(value.get('events',[]),list) or len(value.get('events',[]))>30:auth.error('invalid_events')
            if any(not isinstance(x,str) or not re.fullmatch('[a-z_]{1,60}',x) for x in value.get('events',[])):auth.error('invalid_events')
            if value.get('language','de') not in ['de','en']:auth.error('invalid_language')
            value.update(webhook=webhook,status_message_id=old['status_message_id'] if webhook==old['webhook'] else None)
            st.set('discord',value,True)
        else:
            value={**old,**value}
            if set(value)-{'automatic','check_minutes','backup_minutes','retention_days','backup_enabled','folder_scan_enabled','folder_check_minutes','folder_automatic'}:auth.error('invalid_setting')
            if type(value.get('automatic',False)) is not bool or type(value.get('backup_enabled',False)) is not bool:auth.error('invalid_setting')
            if value.get('automatic') or value.get('folder_automatic'):
                try:readiness=rpc('/maintenance-readiness')
                except Exception:readiness={}
                if not readiness.get('ready'):auth.error('automatic_mod_maintenance_requires_verified_guard',409)
            if not isinstance(value.get('check_minutes'),int) or not 5<=value['check_minutes']<=1440:auth.error('invalid_interval')
            if not isinstance(value.get('backup_minutes'),int) or not 5<=value['backup_minutes']<=1440:auth.error('invalid_interval')
            if not isinstance(value.get('retention_days'),int) or not 1<=value['retention_days']<=90:auth.error('invalid_retention')
            for key in ('folder_scan_enabled','folder_automatic'):
                if type(value.get(key,False)) is not bool:auth.error('invalid_setting')
            if type(value.get('folder_check_minutes',30)) is not int or not 5<=value.get('folder_check_minutes',30)<=1440:auth.error('invalid_interval')
            if value.get('folder_automatic') and (not value.get('folder_scan_enabled',True) or readiness.get('visitor_verified') is not True):auth.error('automatic_mod_maintenance_requires_verified_guard',409)
            prior_approval=st.get('folder_mod_approval') or {}
            st.set('folder_mod_approval',(prior_approval if old.get('folder_automatic') and prior_approval.get('actor')==actor['id'] else {'actor':actor['id'],'at':time.time()}) if value.get('folder_automatic') else None)
            if not value.get('folder_automatic'):automatic.cancel_folder_queued(st)
            st.set('maintenance',value)
            st.set('automatic_mod_approval',{'actor':actor['id'],'at':time.time()} if value.get('automatic') else None)
            if not value.get('automatic'):automatic.cancel_queued(st)
        st.event('settings','configuration_updated',actor['id'],{'section':data.section})
        return {'ok':True}

    @app.post('/api/settings/smtp/test')
    def smtp_test(request:Request):
        actor=user(request,admin=True)
        cfg=st.get('smtp')
        if not cfg.get('host') or not cfg.get('sender'):auth.error('smtp_not_configured',409)
        try:
            return send_email(st,actor['email'],'MCJ Manager – '+('Testmail' if actor['language']=='de' else 'Test email'),
                              'Diese Testmail wurde über deine gespeicherten Maileinstellungen versendet. Wenn du sie lesen kannst, ist der Empfang in deinem Postfach bestätigt. Welche Ereignismeldungen du erhalten möchtest, wählst du im Benutzerprofil.' if actor['language']=='de' else
                              'This test email was sent using your saved mail settings. If you can read it, receipt in your inbox is confirmed. Choose which event notifications you want in your user profile.',actor['id'])
        except RuntimeError:auth.error('smtp_test_failed',502)

    @app.post('/api/settings/discord/test')
    def discord_test(request:Request):
        actor=user(request,admin=True);cfg=st.get('discord')
        if not cfg.get('enabled'):auth.error('discord_disabled',409)
        if not cfg.get('webhook'):auth.error('discord_webhook_required',409)
        try:send_discord(st,'MCJ Manager – '+('Verbindungstest\nDiese Testnachricht wurde über den gespeicherten Webhook gesendet. Welche Ereignisse hier erscheinen, wählst du unter Einstellungen → Discord.' if cfg.get('language','de')=='de' else
                        'Connection test\nThis test message was sent through the saved webhook. Choose which events appear here under Settings → Discord.'),actor=actor['id'])
        except ValueError:auth.error('invalid_discord_webhook',422)
        except RuntimeError:auth.error('discord_test_failed',502)
        return {'ok':True}

    @app.post('/api/settings/discord/webhook/reveal')
    def reveal_discord_webhook(request:Request):
        actor=user(request,admin=True)
        value=st.get('discord').get('webhook','')
        st.event('settings','discord_webhook_viewed',actor['id'])
        return {'webhook':value}

    class Profile(BaseModel):language:str=Field(pattern='^(de|en)$');notifications:dict=Field(default_factory=dict)
    @app.post('/api/profile')
    def profile(data:Profile,request:Request):
        actor=user(request)
        if len(json.dumps(data.notifications))>2000:auth.error('invalid_notifications')
        if set(data.notifications)-{'enabled','categories'}:auth.error('invalid_notifications')
        if type(data.notifications.get('enabled',False)) is not bool:auth.error('invalid_notifications')
        categories=data.notifications.get('categories',[])
        if not isinstance(categories,list) or any(not isinstance(x,str) or x not in dispatch.CATEGORIES for x in categories):auth.error('invalid_notifications')
        with st.db() as db:db.execute('UPDATE users SET language=?,notifications=? WHERE id=?',
            (data.language,json.dumps(data.notifications),actor['id']))
        st.event('user','profile_updated',actor['id'])
        return {'ok':True}

    @app.get('/api/notifications')
    def notification_history(request:Request):
        actor=user(request)
        with st.db() as db:return [dict(x) for x in db.execute('SELECT id,created,channel,state,attempts,error_class FROM notification_outbox WHERE user_id=? ORDER BY id DESC LIMIT 50',(actor['id'],))]

    @app.get('/api/users')
    def users(request:Request):
        user(request,admin=True)
        with st.db() as db:return [dict(x) for x in db.execute('SELECT id,username,email,admin,language,factor,enabled,force_password FROM users WHERE deleted_at IS NULL ORDER BY id')]

    class NewUser(BaseModel):
        username:str=Field(pattern='^[A-Za-z0-9_.-]{2,40}$')
        email:str=Field(min_length=3,max_length=254)
        admin:bool=False
        language:str=Field(default='de',pattern='^(de|en)$')
    @app.post('/api/users')
    def add_user(data:NewUser,request:Request):
        actor=user(request,admin=True)
        if not re.fullmatch(r'[^\s@\r\n]+@[^\s@\r\n]+',data.email):auth.error('invalid_email')
        password=secrets.token_urlsafe(24)
        try:
            with st.db() as db:
                cursor=db.execute('INSERT INTO users(username,email,password,admin,language) VALUES(?,?,?,?,?)',
                    (data.username,data.email,HASHER.hash(password),int(data.admin),data.language))
                identifier=cursor.lastrowid
        except Exception:auth.error('user_creation_failed',409)
        st.event('user','user_created',actor['id'],{'id':identifier,'admin':data.admin})
        return {'id':identifier,'initial_password':password,'change_required':True}

    class UserUpdate(NewUser):enabled:bool=True
    @app.post('/api/users/{identifier}')
    def edit_user(identifier:int,data:UserUpdate,request:Request):
        actor=user(request,admin=True)
        if not re.fullmatch(r'[^\s@\r\n]+@[^\s@\r\n]+',data.email):auth.error('invalid_email')
        if identifier==actor['id'] and (not data.enabled or not data.admin):auth.error('cannot_disable_own_admin',409)
        try:
            with st.db(immediate=True) as db:
                target=db.execute('SELECT * FROM users WHERE id=? AND deleted_at IS NULL',(identifier,)).fetchone()
                if not target:auth.error('user_unavailable',404)
                count=db.execute('SELECT COUNT(*) FROM users WHERE admin=1 AND enabled=1').fetchone()[0]
                if target['admin'] and target['enabled'] and (not data.admin or not data.enabled) and count<=1:auth.error('last_admin_required',409)
                db.execute('UPDATE users SET username=?,email=?,admin=?,language=?,enabled=?,generation=generation+1 WHERE id=?',
                    (data.username,data.email,int(data.admin),data.language,int(data.enabled),identifier))
                db.execute('DELETE FROM sessions WHERE user_id=?',(identifier,))
                db.execute('DELETE FROM challenges WHERE user_id=?',(identifier,))
        except sqlite3.IntegrityError:auth.error('user_update_conflict',409)
        st.event('user','user_updated',actor['id'],{'id':identifier,'admin':data.admin,'enabled':data.enabled})
        return {'ok':True,'sessions_invalidated':True,'login_required':identifier==actor['id']}

    class UserDelete(BaseModel):confirmation:str=Field(min_length=2,max_length=40)

    @app.post('/api/users/{identifier}/delete')
    def delete_user(identifier:int,data:UserDelete,request:Request):
        actor=user(request,admin=True)
        if identifier==actor['id']:auth.error('cannot_delete_own_user',409)
        now=time.time()
        with st.db(immediate=True) as db:
            current=db.execute('SELECT enabled,admin,generation FROM users WHERE id=?',(actor['id'],)).fetchone()
            if not current or not current['enabled'] or not current['admin'] or current['generation']!=actor['generation']:auth.error('authentication_required',401)
            target=db.execute('SELECT * FROM users WHERE id=? AND deleted_at IS NULL',(identifier,)).fetchone()
            if not target:auth.error('user_unavailable',404)
            if data.confirmation!=target['username']:auth.error('user_delete_confirmation_required',409)
            count=db.execute('SELECT COUNT(*) FROM users WHERE admin=1 AND enabled=1 AND deleted_at IS NULL').fetchone()[0]
            if target['admin'] and target['enabled'] and count<=1:auth.error('last_admin_required',409)
            if db.execute("SELECT 1 FROM jobs WHERE actor=? AND state='running'",(identifier,)).fetchone():auth.error('user_has_running_job',409)
            if db.execute("SELECT 1 FROM notification_outbox WHERE user_id=? AND state='sending'",(identifier,)).fetchone():auth.error('user_has_active_delivery',409)
            for table in ['sessions','challenges','recovery_codes']:
                db.execute('DELETE FROM '+table+' WHERE user_id=?',(identifier,))
            db.execute('UPDATE client_pack_links SET revoked=? WHERE actor=? AND revoked IS NULL',(now,identifier))
            db.execute("UPDATE notification_outbox SET state='cancelled' WHERE user_id=? AND state IN ('queued','retry')",(identifier,))
            db.execute("UPDATE jobs SET state='cancelled',updated=?,result=? WHERE actor=? AND state IN ('planned','queued')",(now,json.dumps({'reason':'user_deleted'}),identifier))
            db.execute('DELETE FROM settings WHERE name IN (?,?)',('admin_session_policy:'+str(identifier),'admin_ui_preferences:'+str(identifier)))
            # Keep an anonymous identity for existing audit and download-link references.
            # IDs are never reused, and the removed account cannot be reactivated.
            marker='deleted-'+str(identifier)+'-'+secrets.token_hex(8)
            db.execute("UPDATE users SET username=?,email=?,password='',admin=0,enabled=0,factor=NULL,totp=NULL,totp_last=-1,notifications='{}',generation=generation+1,deleted_at=? WHERE id=?",(marker,marker+'@deleted.invalid',now,identifier))
            db.execute("INSERT INTO events(at,category,event,actor,data) VALUES(?,?,?,?,?)",(now,'user','user_deleted',actor['id'],json.dumps({'id':identifier})))
        return {'ok':True,'sessions_invalidated':True}

    @app.post('/api/users/{identifier}/recovery')
    def begin_factor_recovery(identifier:int,request:Request):
        actor=user(request,admin=True)
        if actor['id']==identifier:auth.error('another_admin_required',409)
        if not st.rate('admin-recovery:'+str(identifier),2,600):auth.error('rate_limited',429)
        with st.db() as db:target=db.execute('SELECT * FROM users WHERE id=? AND enabled=1',(identifier,)).fetchone()
        if not target or not target['factor']:auth.error('user_recovery_unavailable',409)
        target=dict(target)
        token=auth.challenge(st,identifier,'admin_recovery',data=json.dumps({'actor':actor['id'],
            'actor_generation':actor['generation'],'generation':target['generation'],'email':st.digest(target['email'].casefold())}))
        link=canonical_origin()+'/#recover='+token
        de=target['language']=='de'
        body=('Ein anderer angemeldeter Administrator hat die Wiederherstellung deines zweiten Faktors angefordert.\n'
              'Der Link gilt einmalig für 10 Minuten. Zusätzlich brauchst du dein bisheriges Passwort.\n'
              'Wenn du das nicht angefordert hast, öffne den Link nicht und kontaktiere deinen Administrator.\n' if de else
              'Another signed-in administrator requested recovery of your second factor.\n'
              'The link is single-use and valid for 10 minutes. Your existing password is also required.\n'
              'If you did not request this, do not open the link and contact your administrator.\n')+link
        try:auth.send_email(st,target['email'],'MCJ Manager – '+('2FA-Wiederherstellung' if de else '2FA recovery'),body,identifier)
        except Exception:
            with st.db() as db:db.execute('DELETE FROM challenges WHERE token=?',(st.digest(token),))
            st.event('auth','factor_recovery_delivery_failed',actor['id'],{'id':identifier});auth.error('recovery_delivery_failed',503)
        st.event('auth','factor_recovery_requested',actor['id'],{'id':identifier})
        return {'state':'email_sent','existing_password_required':True,'factor_changed':False}

    @app.get('/api/diagnostics')
    def diagnostics(request:Request):
        actor=user(request,admin=True)
        with st.db() as db:
            counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ['users','mods','jobs','backups','events']}
        configured=st.get('server')
        # Free-form properties can contain credentials (including custom mod settings).
        # Support exports contain bounded runtime identifiers, never arbitrary property values.
        server={key:configured.get(key) for key in ['version','java','loader','loader_version','installer_version','memory_mb','world']}
        server['property_count']=len(configured.get('properties',{}))
        result={'version':__version__,'release':st.get('release'),'counts':counts,'server':server,
                'security':{'sessions':'Secure; HttpOnly; SameSite=Strict','password_hash':'Argon2id','secrets':'Fernet',
                            'docker_socket_in_web':False},'generated_at':time.time()}
        st.event('audit','diagnostics_downloaded',actor['id'])
        return JSONResponse(result,headers={'Content-Disposition':'attachment; filename="diagnostics.json"'})

    @app.exception_handler(Exception)
    async def failure(request,exc):
        if isinstance(exc,RuntimeError) and str(exc)=='maintenance_busy':return JSONResponse({'detail':'maintenance_busy'},status_code=409)
        st.event('system','request_failed',data={'error_class':type(exc).__name__})
        return JSONResponse({'detail':'operation_failed'},status_code=503)

    static=Path(__file__).parent/'static'
    @app.get('/favicon.ico',include_in_schema=False)
    def favicon():return FileResponse(static/'favicon.ico',media_type='image/vnd.microsoft.icon')
    app.mount('/static',StaticFiles(directory=static),name='static')
    @app.get('/')
    def index():return FileResponse(static/'index.html')
    return app

import hmac
import json
import secrets
import time
import base64
import qrcode
from qrcode.image.svg import SvgPathFillImage
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictInt
import pyotp
from .store import HASHER
from .notify import send_email
from . import session_policy
from . import email_setup

COOKIE='__Host-mcj'
SESSION_SECONDS=12*60*60
IDLE_SECONDS=4*60*60
PENDING_SECONDS=15*60
router=APIRouter(prefix='/api/auth')
DUMMY=HASHER.hash(secrets.token_urlsafe(24))

def error(code,status=400):raise HTTPException(status,code)
def store(request):return request.app.state.store
def client_address(request):return getattr(request.state,'client_address',request.client.host)

def account(request,verified=False,admin=False):
    st=store(request);raw=request.cookies.get(COOKIE,'');now=time.time()
    with st.db() as db:
        row=db.execute('''SELECT s.token,s.created AS session_created,s.expires,s.last_seen,s.absolute_seconds,s.idle_seconds,s.remember_days,s.mfa,s.generation AS session_generation,u.*
            FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=?''',(st.digest(raw),)).fetchone()
        if not row or row['expires']<=now or now-row['session_created']>=row['absolute_seconds'] or now-row['last_seen']>=row['idle_seconds'] or not row['enabled'] or row['session_generation']!=row['generation']:
            if row:db.execute('DELETE FROM sessions WHERE token=?',(row['token'],))
            row=None
    if row is None:error('authentication_required',401)
    user=dict(row)
    if verified and (user['force_password'] or not user['factor'] or not 0<user['mfa']<=now):error('setup_or_mfa_required',403)
    if admin and not user['admin']:error('admin_required',403)
    # A valid MFA-authenticated session authorises its normal permitted actions.
    # Remembered sessions do not prompt for another factor before their expiry.
    # Reads and automatic dashboard polling never keep an unattended browser signed in.
    if verified and request.method not in ('GET','HEAD','OPTIONS'):
        with st.db() as db:db.execute('UPDATE sessions SET last_seen=? WHERE token=?',(now,user['token']))
    return user

def view(user):
    result={k:user[k] for k in ['id','username','email','admin','language','force_password','factor']}
    result['notifications']=json.loads(user['notifications'])
    return result

def new_session(request,response,user_id,mfa=0,expires_at=None,remember_days=0):
    st=store(request);raw=secrets.token_urlsafe(40);now=time.time()
    with st.db() as db:owner=db.execute('SELECT generation,admin FROM users WHERE id=?',(user_id,)).fetchone()
    policy=session_policy.preference(st,user_id,owner['admin']) if mfa else dict(session_policy.DEFAULT)
    if mfa and remember_days:
        policy={'absolute_seconds':remember_days*86400,'idle_seconds':min(7,remember_days)*86400}
    expires=min(expires_at,now+policy['absolute_seconds']) if expires_at else now+(policy['absolute_seconds'] if mfa else PENDING_SECONDS)
    with st.db() as db:
        generation=db.execute('SELECT generation FROM users WHERE id=?',(user_id,)).fetchone()[0]
        old=request.cookies.get(COOKIE)
        if old:db.execute('DELETE FROM sessions WHERE token=?',(st.digest(old),))
        db.execute('INSERT INTO sessions(token,user_id,created,expires,mfa,generation,ip,last_seen,absolute_seconds,idle_seconds,remember_days) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (st.digest(raw),user_id,now,expires,mfa,generation,client_address(request),now,policy['absolute_seconds'],policy['idle_seconds'],remember_days if mfa else 0))
    response.set_cookie(COOKIE,raw,httponly=True,secure=True,samesite='strict',path='/',max_age=max(0,int(expires-now)))
    return {'csrf':st.digest('csrf:'+raw)}

def challenge(st,user_id,kind,code=None,data=None):
    raw=secrets.token_urlsafe(32)
    with st.db() as db:
        db.execute('INSERT INTO challenges(token,user_id,kind,expires,code,data) VALUES(?,?,?,?,?,?)',
                   (st.digest(raw),user_id,kind,time.time()+600,st.digest(raw+':'+code) if code else None,data))
    return raw

def issue_email(st,user,kind,background,binding=None):
    code=str(secrets.randbelow(1000000)).zfill(6)
    token=secrets.token_urlsafe(32);now=time.time()
    with st.db(immediate=True) as db:
        if binding:
            # Concurrent resends in one pending login reuse its already sent code.
            rows=db.execute('SELECT * FROM challenges WHERE user_id=? AND kind=? AND expires>? ORDER BY expires DESC LIMIT 12',
                            (user['id'],kind,now)).fetchall()
            previous=[]
            for row in rows:
                if not row['data']:continue
                try:data=json.loads(st.open(row['data']))
                except Exception:continue
                if not isinstance(data,dict) or data.get('binding')!=binding:continue
                previous.append(row['token'])
                age=now-(row['expires']-600)
                if age<60 and row['attempts']<5:return data['token']
            for digest in previous:db.execute('DELETE FROM challenges WHERE token=?',(digest,))
        data=st.seal(json.dumps({'binding':binding,'token':token})) if binding else None
        db.execute('INSERT INTO challenges(token,user_id,kind,expires,code,data) VALUES(?,?,?,?,?,?)',
                   (st.digest(token),user['id'],kind,now+600,st.digest(token+':'+code),data))
    purpose={
        'login':('Anmeldung','sign-in'),
        'reauth':('Sicherheitsbestätigung','security confirmation'),
        'enroll_email':('E-Mail-Anmeldung einrichten','set up email sign-in'),
        'reset_factor':('Passwortwiederherstellung','password reset'),
    }.get(kind,('Sicherheitsbestätigung','security confirmation'))
    if user['language']=='de':
        subject='MCJ Manager – Code: '+purpose[0]
        body=f'Dein Sicherheitscode: {code}\n\nWofür: {purpose[0]} im MCJ Manager.\nTrage den Code im geöffneten Manager ein. Er gilt einmalig für 10 Minuten.\n\nWenn du diese Aktion nicht gestartet hast, gib den Code nicht weiter und prüfe dein Konto.\n'
    else:
        subject='MCJ Manager – Code: '+purpose[1]
        body=f'Your security code: {code}\n\nPurpose: {purpose[1]} in MCJ Manager.\nEnter the code in the manager window. It works once and is valid for 10 minutes.\n\nIf you did not start this action, do not share the code and check your account.\n'
    if background is not None:background.add_task(send_email,st,user['email'],subject,body,user['id'])
    else:
        try:send_email(st,user['email'],subject,body,user['id'])
        except Exception:
            with st.db() as db:db.execute('DELETE FROM challenges WHERE token=?',(st.digest(token),))
            raise
    return token

def consume_email(st,user_id,token,code,kind,binding=None):
    with st.db(immediate=True) as db:
        row=db.execute('SELECT * FROM challenges WHERE token=? AND user_id=? AND kind=?',(st.digest(token),user_id,kind)).fetchone()
        if not row or row['expires']<time.time() or row['attempts']>=5:return False
        if binding:
            try:context=json.loads(st.open(row['data']))
            except Exception:return False
            if not isinstance(context,dict) or context.get('binding')!=binding:return False
        db.execute('UPDATE challenges SET attempts=attempts+1 WHERE token=?',(row['token'],))
        good=hmac.compare_digest(row['code'] or '',st.digest(token+':'+code))
        if good:db.execute('DELETE FROM challenges WHERE token=?',(row['token'],))
        return good

def verify_factor(st,user,code,token='',kind='login',recovery=False,binding=None):
    if recovery:return st.consume_recovery(user['id'],code)
    if user['factor']=='email':return consume_email(st,user['id'],token,code,kind,binding)
    if user['factor']=='totp':
        otp=pyotp.TOTP(st.open(user['totp']))
        step=int(time.time()//30)
        with st.db(immediate=True) as db:
            last=db.execute('SELECT totp_last FROM users WHERE id=?',(user['id'],)).fetchone()[0]
            for candidate in [step,step-1,step+1]:
                if candidate>last and hmac.compare_digest(otp.at(candidate*30),code):
                    db.execute('UPDATE users SET totp_last=? WHERE id=?',(candidate,user['id']))
                    return True
    return False

class Login(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=128)


class CompleteRecovery(BaseModel):
    token:str=Field(min_length=30,max_length=100)
    password:str=Field(min_length=1,max_length=128)


@router.post('/recovery/complete')
def complete_recovery(data:CompleteRecovery,request:Request):
    st=store(request)
    if not st.rate('factor-recovery:'+client_address(request),8,600):error('rate_limited',429)
    digest=st.digest(data.token)
    with st.db(immediate=True) as db:
        row=db.execute("SELECT * FROM challenges WHERE token=? AND kind='admin_recovery' AND expires>? AND attempts<5",(digest,time.time())).fetchone()
        if not row:error('invalid_recovery',401)
        db.execute('UPDATE challenges SET attempts=attempts+1 WHERE token=?',(digest,))
        target=db.execute('SELECT * FROM users WHERE id=? AND enabled=1',(row['user_id'],)).fetchone()
    try:good=HASHER.verify(target['password'] if target else DUMMY,data.password)
    except Exception:good=False
    if not target or not good:
        st.event('auth','factor_recovery_failed',row['user_id']);error('invalid_recovery',401)
    with st.db(immediate=True) as db:
        row=db.execute("SELECT * FROM challenges WHERE token=? AND kind='admin_recovery' AND expires>?",(digest,time.time())).fetchone()
        if not row:error('invalid_recovery',401)
        proof=json.loads(row['data'])
        current=db.execute('SELECT * FROM users WHERE id=? AND enabled=1',(target['id'],)).fetchone()
        actor=db.execute('SELECT * FROM users WHERE id=? AND enabled=1 AND admin=1',(proof['actor'],)).fetchone()
        if not current or not actor or current['generation']!=proof['generation'] or actor['generation']!=proof['actor_generation'] or st.digest(current['email'].casefold())!=proof['email']:
            error('invalid_recovery',401)
        db.execute('UPDATE users SET factor=NULL,totp=NULL,totp_last=-1,force_password=1,generation=generation+1 WHERE id=?',(target['id'],))
        for table in ['sessions','challenges','recovery_codes']:db.execute('DELETE FROM '+table+' WHERE user_id=?',(target['id'],))
    st.event('auth','factor_recovery_completed',proof['actor'],{'id':target['id'],'new_password_and_factor_required':True})
    return {'ok':True,'login_required':True,'password_change_required':True,'factor_setup_required':True}

@router.post('/login')
def login(data:Login,request:Request,response:Response,background:BackgroundTasks):
    st=store(request)
    if not st.rate('login-ip:'+client_address(request),20,900) or not st.rate('login-user:'+st.digest(data.username.casefold()),8,900):error('rate_limited',429)
    with st.db() as db:user=db.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE',(data.username,)).fetchone()
    try:good=HASHER.verify(user['password'] if user else DUMMY,data.password)
    except Exception:good=False
    if not user or not user['enabled'] or not good:
        st.event('auth','login_failed',data={'ip':client_address(request),'account_hash':st.digest(data.username.casefold())})
        error('invalid_credentials',401)
    user=dict(user);result=new_session(request,response,user['id'])
    result.update(user=view(user),mfa_required=bool(user['factor']))
    if user['factor']=='email':
        try:result['challenge']=issue_email(st,user,'login',None,binding=result['csrf'])
        except Exception:
            # Keep the password-only session so recovery remains available; do not
            # claim a code was sent or weaken the still-required second factor.
            result['email_delivery_error']='email_login_delivery_failed'
    st.event('auth','password_verified',user['id'],{'ip':client_address(request)})
    return result

@router.get('/me')
def me(request:Request):
    user=account(request)
    from . import setup_wizard
    return {'user':view(user),'mfa_verified':bool(user['mfa']),
            'setup_wizard_pending':bool(user['admin'] and not user['force_password'] and user['factor'] and user['mfa'] and setup_wizard.pending(store(request))),
            'csrf':store(request).digest('csrf:'+request.cookies[COOKIE]),'session':session_policy.view(user)}

@router.get('/session-policy')
def session_preferences(request:Request):
    user=account(request,verified=True,admin=True)
    return {'policy':session_policy.preference(store(request),user['id'],True),'current_session':session_policy.view(user),'server_time':time.time()}

@router.post('/session-policy')
def set_session_preferences(data:session_policy.Policy,request:Request):
    user=account(request,verified=True,admin=True);st=store(request)
    st.set('admin_session_policy:'+str(user['id']),data.seconds())
    st.event('user','session_policy_updated',user['id'],data.seconds())
    return {'policy':data.seconds(),'applies_to':'new_logins'}

@router.post('/activity')
def activity(request:Request):
    account(request,verified=True)
    return {'ok':True}

class Factor(BaseModel):
    code:str=Field(min_length=1,max_length=100)
    challenge:str=Field(default='',max_length=200)
    recovery:bool=False

class LoginFactor(Factor):
    remember_days:StrictInt=Field(default=0,ge=0,le=30)

@router.post('/verify')
def verify(data:LoginFactor,request:Request,response:Response):
    st=store(request);user=account(request)
    if user['mfa']:error('already_authenticated',409)
    if not st.rate('factor:'+str(user['id']),12,600):error('rate_limited',429)
    if not verify_factor(st,user,data.code,data.challenge,recovery=data.recovery,binding=st.digest('csrf:'+request.cookies[COOKIE])):
        st.event('auth','factor_failed',user['id']);error('invalid_factor',401)
    result=new_session(request,response,user['id'],time.time(),remember_days=data.remember_days)
    st.event('auth','login_success',user['id'],{'ip':client_address(request)})
    return result

@router.post('/reauth/challenge')
def reauth_challenge(request:Request,background:BackgroundTasks):
    st=store(request);user=account(request,verified=True)
    if user['factor']!='email':return {'challenge':''}
    if not st.rate('reauth-email:'+str(user['id']),3,600):error('rate_limited',429)
    return {'challenge':issue_email(st,user,'reauth',background,binding=st.digest('csrf:'+request.cookies[COOKIE]))}

@router.post('/reauth')
def reauthenticate(data:Factor,request:Request):
    st=store(request);user=account(request,verified=True)
    if not st.rate('reauth:'+str(user['id']),12,600):error('rate_limited',429)
    if not verify_factor(st,user,data.code,data.challenge,kind='reauth',recovery=data.recovery,binding=st.digest('csrf:'+request.cookies[COOKIE])):
        error('invalid_factor',401)
    now=time.time()
    # Recheck the account generation and expiry under the write lock. Reauthentication
    # renews assurance, never the absolute lifetime or idle limit of the cookie.
    with st.db(immediate=True) as db:
        changed=db.execute('''UPDATE sessions SET mfa=?,last_seen=? WHERE token=? AND expires>? AND created+absolute_seconds>? AND last_seen+idle_seconds>?
            AND EXISTS(SELECT 1 FROM users WHERE id=sessions.user_id AND enabled=1 AND generation=sessions.generation)''',
            (now,now,user['token'],now,now,now)).rowcount
    if changed!=1:error('authentication_required',401)
    st.event('auth','session_reauthenticated',user['id'])
    return {'ok':True}

@router.get('/sessions')
def sessions(request:Request):
    user=account(request,verified=True);st=store(request);now=time.time()
    with st.db() as db:
        rows=db.execute('''SELECT * FROM sessions WHERE user_id=? AND mfa>0 AND generation=? AND expires>?
            AND created+absolute_seconds>? AND last_seen+idle_seconds>? ORDER BY created DESC LIMIT 100''',
            (user['id'],user['generation'],now,now,now)).fetchall()
    return [{'id':st.digest('session-id:'+row['token'])[:32],'created':row['created'],'last_seen':row['last_seen'],
             'expires':row['expires'],'remember_days':row['remember_days'],'current':row['token']==user['token']} for row in rows]

class RevokeSession(BaseModel):
    identifier:str=Field(pattern=r'^(others|[a-f0-9]{32})$')

@router.post('/sessions/revoke')
def revoke_session(data:RevokeSession,request:Request):
    user=account(request,verified=True);st=store(request)
    with st.db(immediate=True) as db:
        if data.identifier=='others':
            changed=db.execute('DELETE FROM sessions WHERE user_id=? AND token<>?',(user['id'],user['token'])).rowcount
        else:
            rows=db.execute('SELECT token FROM sessions WHERE user_id=?',(user['id'],)).fetchall()
            target=next((row['token'] for row in rows if hmac.compare_digest(st.digest('session-id:'+row['token'])[:32],data.identifier)),None)
            if not target:error('session_not_found',404)
            changed=db.execute('DELETE FROM sessions WHERE token=? AND user_id=?',(target,user['id'])).rowcount
    st.event('auth','sessions_revoked',user['id'],{'count':changed})
    return {'ok':True}

@router.post('/email-challenge')
def email_challenge(request:Request,background:BackgroundTasks):
    st=store(request);user=account(request)
    if user['mfa']:error('already_authenticated',409)
    if user['factor']!='email':error('email_factor_unavailable')
    if not st.rate('email-factor:'+str(user['id']),3,600):error('rate_limited',429)
    try:return {'challenge':issue_email(st,user,'login',None,binding=st.digest('csrf:'+request.cookies[COOKIE]))}
    except Exception:error('email_login_delivery_failed',502)

@router.post('/logout')
def logout(request:Request,response:Response):
    st=store(request);user=account(request)
    with st.db() as db:db.execute('DELETE FROM sessions WHERE token=?',(user['token'],))
    response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict')
    st.event('auth','logout',user['id'])
    return {'ok':True}

class Password(BaseModel):
    current:str=Field(min_length=1,max_length=128)
    password:str=Field(min_length=12,max_length=128)

@router.post('/password')
def password(data:Password,request:Request,response:Response):
    st=store(request);user=account(request,verified=False)
    if user['factor']:account(request,verified=True)
    try:HASHER.verify(user['password'],data.current)
    except Exception:error('invalid_credentials',401)
    if data.password==data.current:error('password_must_change')
    with st.db() as db:
        db.execute('UPDATE users SET password=?,force_password=0,generation=generation+1 WHERE id=?',(HASHER.hash(data.password),user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    st.event('auth','password_changed',user['id'])
    from .first_login import consume_file
    consume_file(st,user)
    return new_session(request,response,user['id'],user['mfa'],expires_at=user['expires'],remember_days=user['remember_days'])

def can_enroll(request):
    user=account(request)
    if user['force_password']:error('password_change_required',403)
    if user['factor']:user=account(request,verified=True)
    return user

@router.post('/setup/totp')
def setup_totp(request:Request):
    st=store(request);user=can_enroll(request)
    secret=pyotp.random_base32()
    token=challenge(st,user['id'],'enroll_totp',data=st.seal(secret))
    uri=pyotp.TOTP(secret).provisioning_uri(user['email'],issuer_name='MCJ Manager')
    # Generated locally: no enrollment secret is sent to a QR service.
    image=qrcode.make(uri,image_factory=SvgPathFillImage,border=4)
    qr='data:image/svg+xml;base64,'+base64.b64encode(image.to_string()).decode('ascii')
    return {'challenge':token,'secret':secret,'uri':uri,'qr':qr}

@router.post('/setup/email')
def setup_email(request:Request,background:BackgroundTasks):
    st=store(request);user=can_enroll(request)
    return email_setup.start(st,user,st.digest('csrf:'+request.cookies[COOKIE]),send_email)

@router.get('/setup/email/status')
def email_setup_status(request:Request):
    user=can_enroll(request);settings=store(request).get('smtp')
    return {'configured':email_setup.configured(settings),
            'can_configure':email_setup.can_configure(user,settings)}

@router.post('/setup/email/smtp')
def email_setup_smtp(data:email_setup.MailSettings,request:Request):
    st=store(request);user=can_enroll(request)
    if not user['admin']:error('admin_required',403)
    return email_setup.start(st,user,st.digest('csrf:'+request.cookies[COOKIE]),send_email,data.model_dump())

class Enroll(Factor):
    method:str=Field(pattern='^(totp|email)$')

@router.post('/setup/confirm')
def setup_confirm(data:Enroll,request:Request,response:Response):
    st=store(request);user=can_enroll(request)
    if not st.rate('enroll:'+str(user['id']),10,600):error('rate_limited',429)
    secret=None;matched_step=-1
    if data.method=='email':good=email_setup.confirm(st,user,st.digest('csrf:'+request.cookies[COOKIE]),data.challenge,data.code)
    else:
        with st.db(immediate=True) as db:
            row=db.execute('SELECT * FROM challenges WHERE token=? AND user_id=? AND kind=?',(st.digest(data.challenge),user['id'],'enroll_totp')).fetchone()
            good=False
            if row and row['expires']>time.time() and row['attempts']<5:
                db.execute('UPDATE challenges SET attempts=attempts+1 WHERE token=?',(row['token'],))
                secret=st.open(row['data']);otp=pyotp.TOTP(secret);step=int(time.time()//30)
                for candidate in [step,step-1,step+1]:
                    if hmac.compare_digest(otp.at(candidate*30),data.code):good=True;matched_step=candidate;break
                if good:db.execute('DELETE FROM challenges WHERE token=?',(row['token'],))
    if not good:error('email_setup_code_invalid' if data.method=='email' else 'invalid_factor',401)
    if data.method=='totp':
        with st.db() as db:
            db.execute('UPDATE users SET factor=?,totp=?,totp_last=?,generation=generation+1 WHERE id=?',
                       (data.method,st.seal(secret) if secret else None,matched_step if secret else -1,user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    result=new_session(request,response,user['id'],time.time());result['backup_codes']=st.recovery(user['id'])
    st.event('auth','factor_configured',user['id'],{'method':data.method})
    return result

@router.post('/backup-codes')
def backup_codes(request:Request):
    user=account(request,verified=True);st=store(request)
    codes=st.recovery(user['id']);st.event('auth','recovery_codes_regenerated',user['id'])
    return {'backup_codes':codes}

class Forgot(BaseModel):email:str=Field(min_length=3,max_length=254)

class Language(BaseModel):language:str=Field(pattern='^(de|en)$')

@router.post('/language')
def language(data:Language,request:Request):
    user=account(request);st=store(request)
    with st.db() as db:db.execute('UPDATE users SET language=? WHERE id=?',(data.language,user['id']))
    return {'ok':True}

@router.post('/forgot')
def forgot(data:Forgot,request:Request,background:BackgroundTasks):
    st=store(request)
    if not st.rate('forgot-ip:'+client_address(request),6,900):error('rate_limited',429)
    if not st.rate('forgot-mail:'+st.digest(data.email.casefold()),3,900):return {'status':'request_received'}
    with st.db() as db:user=db.execute('SELECT * FROM users WHERE email=? COLLATE NOCASE AND enabled=1',(data.email,)).fetchone()
    if user:
        user=dict(user);token=challenge(st,user['id'],'reset')
        link=request.app.state.origin+'/#reset='+token
        subject='MCJ Manager – '+('Passwort zurücksetzen' if user['language']=='de' else 'Reset your password')
        body=(('Für dein Konto wurde ein Link angefordert, um das Passwort im MCJ Manager zurückzusetzen.\n\nDer Link funktioniert einmal und gilt für 10 Minuten. Dein Passwort wurde durch diese E-Mail noch nicht geändert.\nWenn du den Link nicht angefordert hast, öffne ihn nicht.\n\nÖffne dafür diesen Link:\n'+link) if user['language']=='de' else
              ('A link was requested to reset your MCJ Manager password.\n\nThe link works once and is valid for 10 minutes. This email has not changed your password.\nIf you did not request the link, do not open it.\n\nOpen this link to continue:\n'+link))
        background.add_task(send_email,st,user['email'],subject,body,user['id'])
        st.event('auth','password_reset_requested',user['id'])
    return {'status':'request_received'}

class ResetLink(BaseModel):
    token:str=Field(min_length=20,max_length=200)


def reset_link_user(st,token):
    with st.db() as db:
        row=db.execute('SELECT u.*,c.expires AS reset_expires FROM challenges c JOIN users u ON u.id=c.user_id WHERE c.token=? AND c.kind=? AND u.enabled=1',
                       (st.digest(token),'reset')).fetchone()
    if not row or row['reset_expires']<=time.time():
        st.event('auth','password_reset_link_rejected',row['id'] if row else None,
                 {'reason':'expired' if row else 'unknown_or_used'})
        error('invalid_reset')
    return dict(row)


@router.post('/reset/context')
def reset_context(data:ResetLink,request:Request):
    st=store(request)
    if not st.rate('reset-context:'+client_address(request),12,600):error('rate_limited',429)
    user=reset_link_user(st,data.token)
    return {'username':user['username'],'factor':user['factor'] or None,
            'initial_setup':not bool(user['factor']),'expires_at':user['reset_expires']}


class Reset(ResetLink):
    password:str=Field(min_length=12,max_length=128)
    code:str=Field(default='',max_length=100)
    challenge:str=Field(default='',max_length=200)
    recovery:bool=False

@router.post('/reset/email-challenge')
def reset_email(data:Reset,request:Request,background:BackgroundTasks):
    st=store(request)
    if not st.rate('reset-email:'+client_address(request),5,600):error('rate_limited',429)
    user=reset_link_user(st,data.token)
    if user['factor']!='email':error('invalid_reset')
    return {'challenge':issue_email(st,user,'reset_factor',background)}

@router.post('/reset')
def reset(data:Reset,request:Request):
    st=store(request)
    if not st.rate('reset:'+client_address(request),8,600):error('rate_limited',429)
    user=reset_link_user(st,data.token)
    if user['factor'] and not verify_factor(st,user,data.code,data.challenge,'reset_factor',data.recovery):error('invalid_factor',401)
    hashed=HASHER.hash(data.password)
    with st.db(immediate=True) as db:
        consumed=db.execute('DELETE FROM challenges WHERE token=? AND kind=? AND expires>?',(st.digest(data.token),'reset',time.time())).rowcount
        if consumed!=1:error('invalid_reset')
        db.execute('UPDATE users SET password=?,force_password=0,generation=generation+1 WHERE id=?',(hashed,user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    st.event('auth','password_reset_complete',user['id'])
    return {'ok':True}

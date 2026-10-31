"""Durable configuration and secret storage. Never log arbitrary request bodies."""
import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import threading
from argon2 import PasswordHasher, Type
from cryptography.fernet import Fernet

class BoundedPasswordHasher:
    def __init__(self):
        self.hasher=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=4,type=Type.ID)
        self.slots=threading.BoundedSemaphore(2)
    def hash(self,password):
        with self.slots:return self.hasher.hash(password)
    def verify(self,encoded,password):
        with self.slots:return self.hasher.verify(encoded,password)

HASHER = BoundedPasswordHasher()
_change_locks={}
_change_locks_guard=threading.Lock()
_change_depth=threading.local()


class Store:
    @contextlib.contextmanager
    def change_lock(self):
        """Serialize mod/config mutations with an in-flight tested promotion."""
        key=str(self.state.resolve())
        with _change_locks_guard:lock=_change_locks.setdefault(key,threading.RLock())
        if not lock.acquire(blocking=False):raise RuntimeError('maintenance_busy')
        depths=getattr(_change_depth,'held',{});_change_depth.held=depths
        fd=None
        try:
            if not depths.get(key):
                fd=os.open(self.state/'.changes.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
                if os.name!='nt':
                    import fcntl
                    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:raise RuntimeError('maintenance_busy') from None
            depths[key]=depths.get(key,0)+1
            try:yield
            finally:
                depths[key]-=1
                if not depths[key]:del depths[key]
        finally:
            if fd is not None:os.close(fd)
            lock.release()

    def __init__(self, state, keyfile, bootstrap=None, *, initial_accounts=None):
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        keyfile = Path(keyfile)
        if not keyfile.is_file():
            raise RuntimeError('Encryption key missing: explicit recovery required')
        if os.name != 'nt' and keyfile.stat().st_mode & 0o037:
            raise RuntimeError('Encryption key permissions must be 0640 or stricter')
        self.key = keyfile.read_bytes().strip()
        self.cipher = Fernet(self.key)
        self.path = self.state / 'manager.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE NOT NULL,
              email TEXT UNIQUE COLLATE NOCASE NOT NULL, password TEXT NOT NULL,
              admin INTEGER NOT NULL DEFAULT 0, language TEXT NOT NULL DEFAULT 'de',
              force_password INTEGER NOT NULL DEFAULT 1, factor TEXT,
              totp TEXT, totp_last INTEGER NOT NULL DEFAULT -1, enabled INTEGER NOT NULL DEFAULT 1,
              generation INTEGER NOT NULL DEFAULT 0, notifications TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS sessions(
              token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
              created REAL NOT NULL,expires REAL NOT NULL,mfa REAL NOT NULL DEFAULT 0,
              generation INTEGER NOT NULL,ip TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS challenges(
              token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),kind TEXT NOT NULL,
              expires REAL NOT NULL,code TEXT,attempts INTEGER NOT NULL DEFAULT 0,data TEXT);
            CREATE TABLE IF NOT EXISTS recovery_codes(
              user_id INTEGER NOT NULL REFERENCES users(id),hash TEXT NOT NULL,used REAL,
              PRIMARY KEY(user_id,hash));
            CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,value TEXT NOT NULL,secret INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL NOT NULL,category TEXT NOT NULL,
              event TEXT NOT NULL,actor INTEGER,data TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS rate_limits(bucket TEXT NOT NULL,at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS client_packs(id TEXT PRIMARY KEY,number INTEGER UNIQUE NOT NULL,
              created REAL NOT NULL,actor INTEGER NOT NULL,fingerprint TEXT NOT NULL,sha256 TEXT NOT NULL,
              size INTEGER NOT NULL,manifest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS client_pack_links(id TEXT PRIMARY KEY,pack_id TEXT NOT NULL REFERENCES client_packs(id),
              actor INTEGER NOT NULL REFERENCES users(id),created REAL NOT NULL,expires REAL NOT NULL,
              token_hash TEXT UNIQUE NOT NULL,revoked REAL);
            CREATE TABLE IF NOT EXISTS guard_events(key TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS player_greeting_history(uuid TEXT PRIMARY KEY,first_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS notification_outbox(id INTEGER PRIMARY KEY,channel TEXT NOT NULL,
              user_id INTEGER,created REAL NOT NULL,event_ids TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'queued',
              attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL DEFAULT 0,error_class TEXT);
            CREATE INDEX IF NOT EXISTS rate_bucket ON rate_limits(bucket,at);
            CREATE TABLE IF NOT EXISTS mods(id TEXT PRIMARY KEY,filename TEXT NOT NULL,sha256 TEXT NOT NULL,
              metadata TEXT NOT NULL,source TEXT NOT NULL,state TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
              available TEXT,error TEXT,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,
              created REAL NOT NULL,updated REAL NOT NULL,actor INTEGER,mode TEXT NOT NULL,
              payload TEXT NOT NULL,result TEXT,approved INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS backups(id TEXT PRIMARY KEY,created REAL NOT NULL,kind TEXT NOT NULL,
              state TEXT NOT NULL,path TEXT,size INTEGER,sha256 TEXT,verified REAL,restored REAL,error TEXT);
            CREATE TABLE IF NOT EXISTS players(uuid TEXT PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'visitor',
              first_seen REAL NOT NULL,last_seen REAL,online_since REAL,play_seconds INTEGER NOT NULL DEFAULT 0,
              banned INTEGER NOT NULL DEFAULT 0,ban_reason TEXT,whitelisted INTEGER NOT NULL DEFAULT 0,op INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS version_plans(id TEXT PRIMARY KEY,created REAL NOT NULL,actor INTEGER,
              configuration TEXT NOT NULL,report TEXT NOT NULL,state TEXT NOT NULL,based_on TEXT NOT NULL,
              test_result TEXT,backup_id TEXT,image_id TEXT,updated REAL);
            ''')
            # Manager and controller can start together; serialize schema inspection and migration.
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            session_columns={row['name'] for row in db.execute('PRAGMA table_info(sessions)')}
            if 'last_seen' not in session_columns:
                db.execute('ALTER TABLE sessions ADD COLUMN last_seen REAL NOT NULL DEFAULT 0')
                # Existing sessions retain their original authentication and absolute deadline.
                db.execute('UPDATE sessions SET last_seen=MAX(created,mfa)')
            backup_columns={row['name'] for row in db.execute('PRAGMA table_info(backups)')}
            for column,default in [('absolute_seconds',43200),('idle_seconds',14400)]:
                if column not in session_columns:db.execute('ALTER TABLE sessions ADD COLUMN '+column+' INTEGER NOT NULL DEFAULT '+str(default))
            if 'remember_days' not in session_columns:
                db.execute('ALTER TABLE sessions ADD COLUMN remember_days INTEGER NOT NULL DEFAULT 0')
            for column,kind in [('restore_tested','REAL'),('restore_status','TEXT')]:
                if column not in backup_columns:db.execute('ALTER TABLE backups ADD COLUMN '+column+' '+kind)
            db.execute('CREATE INDEX IF NOT EXISTS backups_created_id ON backups(created DESC,id DESC)')
            mod_columns={row['name'] for row in db.execute('PRAGMA table_info(mods)')}
            plan_columns={row['name'] for row in db.execute('PRAGMA table_info(version_plans)')}
            if 'mod_fingerprint' not in plan_columns:db.execute('ALTER TABLE version_plans ADD COLUMN mod_fingerprint TEXT')
            if 'installed_enabled' not in mod_columns:
                db.execute('ALTER TABLE mods ADD COLUMN installed_enabled INTEGER NOT NULL DEFAULT 0')
                db.execute("UPDATE mods SET installed_enabled=enabled WHERE state='installed'")
            if 'replaces' not in mod_columns:db.execute('ALTER TABLE mods ADD COLUMN replaces TEXT')
            if 'origin' not in mod_columns:db.execute('ALTER TABLE mods ADD COLUMN origin TEXT')
            if 'remove_pending' not in mod_columns:db.execute('ALTER TABLE mods ADD COLUMN remove_pending INTEGER')
            user_columns={row['name'] for row in db.execute('PRAGMA table_info(users)')}
            if 'deleted_at' not in user_columns:db.execute('ALTER TABLE users ADD COLUMN deleted_at REAL')
            count = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            if not count:
                passwords = {}
                # Explicit fresh-install inputs never change accounts in an existing database.
                accounts=initial_accounts if initial_accounts is not None else [
                    {'username':'Owner','email':'owner@example.invalid'}]
                if not isinstance(accounts,list) or not 1<=len(accounts)<=10:
                    raise ValueError('initial_accounts_invalid')
                usernames=set();emails=set()
                for item in accounts:
                    if not isinstance(item,dict) or set(item)-{'username','email','password'}:
                        raise ValueError('initial_accounts_invalid')
                    name=item.get('username');email=item.get('email');password=item.get('password')
                    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{2,40}',name):
                        raise ValueError('initial_accounts_invalid')
                    if not isinstance(email,str) or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
                        raise ValueError('initial_accounts_invalid')
                    if name.casefold() in usernames or email.casefold() in emails:
                        raise ValueError('initial_accounts_invalid')
                    if password is not None and (not isinstance(password,str) or not 12<=len(password)<=128):
                        raise ValueError('initial_accounts_invalid')
                    usernames.add(name.casefold());emails.add(email.casefold())
                for item in accounts:
                    name=item['username'];email=item['email']
                    password = item.get('password') or secrets.token_urlsafe(24)
                    db.execute('INSERT INTO users(username,email,password,admin) VALUES(?,?,?,1)',
                               (name,email,HASHER.hash(password)))
                    passwords[name] = {'email':email,'password':password}
                if bootstrap:
                    self.atomic(Path(bootstrap), self.cipher.encrypt(json.dumps(passwords).encode()), 0o600)
        if os.name != 'nt': os.chmod(self.path,0o600)
        self.default('server', {'version':'26.3','java':25,'loader':'FABRIC','loader_version':'0.20.1','installer_version':'1.1.2',
                               'memory_mb':6144,'world':'world','properties':{'online-mode':'true','gamemode':'spectator',
                               'force-gamemode':'true','white-list':'true','difficulty':'normal','pvp':'false','max-players':'20'}})
        self.default('maintenance',{'automatic':False,'check_minutes':30,'backup_minutes':30,'retention_days':14,'backup_enabled':True})
        self.default('runtime_cleanup',{'enabled':False,'retention_days':14})
        self.default('smtp',{'host':'','port':587,'security':'starttls',
                            'username':'','sender':'','password':''},True)
        self.default('discord',{'enabled':False,'webhook':'','events':[],'status_message_id':None},True)
        from .greetings import DEFAULTS as GREETINGS
        self.default('greetings',GREETINGS)
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO player_greeting_history SELECT uuid,first_seen FROM players')
        self.default('providers',{'curseforge_api_key':''},True)
        self.default('mod_sources',[])
        self.default('release',{'status':'internal_validation','public_web':False,'public_game':False,
                             'visitor_verified':False,'restore_verified':False,'security_verified':False})

    @contextlib.contextmanager
    def db(self, immediate=False):
        db = sqlite3.connect(self.path,timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        try:
            if immediate: db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally: db.close()

    @staticmethod
    def atomic(path, value, mode=0o600):
        path = Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp = path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
        fd = os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
        try:
            with os.fdopen(fd,'wb') as f:
                # Explicit saved modes must survive a restrictive installer/CI umask,
                # including the read-only executable startup script during rollback.
                if os.name!='nt':os.fchmod(f.fileno(),mode & 0o777)
                f.write(value); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,path)
            if os.name != 'nt':
                dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(dfd)
                finally:os.close(dfd)
        finally:
            if tmp.exists():tmp.unlink()

    def digest(self,value):
        return hmac.new(self.key,value.encode(),hashlib.sha256).hexdigest()

    def seal(self,value): return self.cipher.encrypt(value.encode()).decode()
    def open(self,value): return self.cipher.decrypt(value.encode()).decode()

    def default(self,name,value,secret=False):
        with self.db() as db:
            if not db.execute('SELECT 1 FROM settings WHERE name=?',(name,)).fetchone():
                raw=json.dumps(value)
                db.execute('INSERT INTO settings VALUES(?,?,?)',(name,self.seal(raw) if secret else raw,int(secret)))

    def get(self,name):
        with self.db() as db: row=db.execute('SELECT * FROM settings WHERE name=?',(name,)).fetchone()
        if not row:return None
        value=json.loads(self.open(row['value']) if row['secret'] else row['value'])
        if name=='server' and isinstance(value,dict):
            from .server_settings import SECRET_KEYS
            value['properties']={k:v for k,v in value.get('properties',{}).items() if k not in SECRET_KEYS}
        return value

    def set(self,name,value,secret=False):
        raw=json.dumps(value,ensure_ascii=False)
        with self.db() as db:
            db.execute('INSERT INTO settings VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=excluded.secret',
                       (name,self.seal(raw) if secret else raw,int(secret)))

    def event(self,category,event,actor=None,data=None):
        # Callers supply bounded structured fields, never passwords, OTPs, raw URLs or request bodies.
        with self.db() as db:
            db.execute('INSERT INTO events(at,category,event,actor,data) VALUES(?,?,?,?,?)',
                       (time.time(),category,event,actor,json.dumps(data or {},ensure_ascii=False)))

    def rate(self,bucket,limit,seconds):
        now=time.time()
        with self.db(immediate=True) as db:
            db.execute('DELETE FROM rate_limits WHERE at<?',(now-86400,))
            count=db.execute('SELECT COUNT(*) FROM rate_limits WHERE bucket=? AND at>?',(bucket,now-seconds)).fetchone()[0]
            if count>=limit:return False
            db.execute('INSERT INTO rate_limits VALUES(?,?)',(bucket,now))
            return True

    def sqlite_backup(self,path):
        destination=sqlite3.connect(path)
        try:
            with self.db() as source:source.backup(destination)
            result=destination.execute('PRAGMA integrity_check').fetchone()[0]
            if result!='ok':raise RuntimeError('SQLite backup failed integrity check')
        finally:destination.close()

    def recovery(self,user_id):
        codes=[secrets.token_hex(8).upper() for _ in range(10)]
        with self.db(immediate=True) as db:
            db.execute('DELETE FROM recovery_codes WHERE user_id=?',(user_id,))
            db.executemany('INSERT INTO recovery_codes(user_id,hash) VALUES(?,?)',[(user_id,self.digest(x)) for x in codes])
        return codes

    def consume_recovery(self,user_id,code):
        code=re.sub(r'[\s-]','',code).upper()
        with self.db(immediate=True) as db:
            changed=db.execute('UPDATE recovery_codes SET used=? WHERE user_id=? AND hash=? AND used IS NULL',
                               (time.time(),user_id,self.digest(code))).rowcount
        if changed:self.event('auth','recovery_code_used',user_id)
        return changed==1

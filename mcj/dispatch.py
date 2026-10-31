"""Durable, bounded notification delivery without feeding mail events back into mail."""
from datetime import datetime
import json
import time
from . import notify
from . import notification_text
from .notification_policy import visible_to

CATEGORIES={'auth','server','mods','backup','maintenance','system','player','user','audit'}
LABELS={
 'auth':('Anmeldung und Sicherheit','Authentication and security'),
 'server':('Server','Server'),'mods':('Mods','Mods'),'backup':('Backup','Backup'),
 'maintenance':('Wartung','Maintenance'),'system':('System','System'),
 'player':('Spieler','Players'),'user':('Web-Benutzer','Web users'),'audit':('Audit','Audit'),
 'backup_verified':('Backup erstellt und geprüft','Backup created and verified'),
 'backup_failed':('Backup fehlgeschlagen','Backup failed'),
 'backup_restored':('Backup wiederhergestellt','Backup restored'),
 'restore_test_passed':('Isolierter Restore bestanden','Isolated restore passed'),
 'version_applied':('Serverversion angewendet','Server version applied'),
 'mods_applied':('Mods angewendet','Mods applied'),
 'version_test_passed':('Isolierter Versionstest bestanden','Isolated version test passed'),
 'version_test_failed':('Isolierter Versionstest fehlgeschlagen','Isolated version test failed'),
 'login_success':('Anmeldung erfolgreich','Sign-in successful'),
 'login_failed':('Anmeldung fehlgeschlagen','Sign-in failed'),
 'factor_failed':('Sicherheitscode abgewiesen','Security code rejected'),
 'password_reset_requested':('Passwort-Zurücksetzung angefordert','Password reset requested'),
 'password_reset_complete':('Passwort zurückgesetzt','Password reset completed'),
 'password_changed':('Passwort geändert','Password changed'),
 'factor_configured':('Sichere Anmeldung eingerichtet','Secure sign-in set up'),
 'player_login':('Spieler verbunden','Player connected'),
 'player_logout':('Spieler getrennt','Player disconnected'),
 'player_role':('Spielergruppe geändert','Player group changed'),
 'player_ban':('Spieler gesperrt','Player banned'),
 'player_unban':('Spielersperre aufgehoben','Player unbanned'),
 'server_start':('Server gestartet','Server started'),
 'server_stop':('Server gestoppt','Server stopped'),
 'server_restart':('Server neu gestartet','Server restarted'),
 'chat_sent':('Chatnachricht gesendet','Chat message sent'),
 'job_failed':('Wartungsauftrag fehlgeschlagen','Maintenance job failed'),
 'change_rolled_back':('Änderung zurückgerollt','Change rolled back'),
 'update_check_completed':('Mod-Update-Prüfung abgeschlossen','Mod update check completed'),
 'source_list_updated':('Mod-Quellen aktualisiert','Mod sources updated'),
 'user_updated':('Web-Benutzer geändert','Web user updated'),
 'factor_recovery_requested':('2FA-Wiederherstellung angefordert','2FA recovery requested'),
 'factor_recovery_completed':('2FA-Wiederherstellung bestätigt','2FA recovery confirmed'),
 'factor_recovery_failed':('2FA-Wiederherstellung abgewiesen','2FA recovery rejected'),
 'factor_recovery_delivery_failed':('2FA-Wiederherstellungs-E-Mail fehlgeschlagen','2FA recovery email failed'),
 'world_import_staged':('Weltimport vorgemerkt','World import staged'),
 'automatic_mod_maintenance_queued':('Automatische Mod-Wartung vorgemerkt','Automatic mod maintenance queued'),
 'automatic_mod_staging_failed':('Automatische Mod-Vorbereitung fehlgeschlagen','Automatic mod staging failed'),
 'source_staged':('Dateien aus Mod-Quelle vorgemerkt','Mod source files staged'),
 'source_files_staged':('Mod-Dateien vorgemerkt','Mod files staged'),
 'pack_staged':('Modpack vorgemerkt','Modpack staged'),
 'pack_properties_selected':('Pack-Servereinstellungen ausgewählt','Pack server settings selected'),
 'request_failed':('Anfrage fehlgeschlagen','Request failed'),
 'worker_error':('Hintergrundauftrag fehlgeschlagen','Background job failed'),
 'minecraft_permissions_updated':('Minecraft-Berechtigungen geändert','Minecraft permissions updated'),
 'player_moderation':('Spielaktion autorisiert','In-game action authorized'),
 'backup_retention_failed':('Aufbewahrung konnte nicht bereinigt werden','Retention cleanup failed')}

def render(events,language,origin,store=None,channel='email'):
    return notification_text.render(events,language,origin,LABELS,store,channel)

def queue_events(store):
    with store.db(immediate=True) as db:
        saved=db.execute("SELECT value FROM settings WHERE name='notification_cursor'").fetchone()
        cursor=json.loads(saved['value']) if saved else db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]
        events=[dict(x) for x in db.execute('SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100',(cursor,))]
        if events:
            for user in db.execute('SELECT id,enabled,admin,notifications FROM users WHERE enabled=1'):
                preferences=json.loads(user['notifications'])
                selected=[x['id'] for x in events if x['category'] in CATEGORIES and x['category'] in preferences.get('categories',[]) and visible_to(user,x)] if preferences.get('enabled') else []
                if selected:db.execute('INSERT INTO notification_outbox(channel,user_id,created,event_ids) VALUES(?,?,?,?)',('email',user['id'],time.time(),json.dumps(selected)))
            discord=store.get('discord')
            selected=[x['id'] for x in events if x['category'] in CATEGORIES and (x['category'] in discord.get('events',[]) or x['event'] in discord.get('events',[]))]
            if discord.get('enabled') and selected:
                db.execute('INSERT INTO notification_outbox(channel,created,event_ids) VALUES(?,?,?)',('discord',time.time(),json.dumps(selected)))
            cursor=events[-1]['id']
        db.execute('INSERT INTO settings VALUES(?,?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value,secret=0',('notification_cursor',json.dumps(cursor)))

def dispatch_one(store,origin):
    with store.db(immediate=True) as db:
        record=db.execute("SELECT * FROM notification_outbox WHERE state='queued' AND next_at<=? ORDER BY id LIMIT 1",(time.time(),)).fetchone()
        if not record:return False
        record=dict(record)
        db.execute("UPDATE notification_outbox SET state='sending',attempts=attempts+1 WHERE id=?",(record['id'],))
        identifiers=json.loads(record['event_ids'])
        events=[dict(x) for x in db.execute('SELECT * FROM events WHERE id IN ('+','.join('?' for _ in identifiers)+') ORDER BY id',identifiers)]
        user=db.execute('SELECT * FROM users WHERE id=?',(record['user_id'],)).fetchone() if record['channel']=='email' else None
    try:
        if record['channel']=='email':
            prefs=json.loads(user['notifications']) if user else {}
            selected=[x for x in events if x['category'] in prefs.get('categories',[]) and visible_to(user,x)]
            if not user or not user['enabled'] or not prefs.get('enabled') or not selected:state='cancelled'
            else:
                subject,body=render(selected,user['language'],origin,store)
                result=notify.send_email(store,user['email'],subject,body,user['id'])
                state='accepted_by_test_transport' if result.get('status')=='accepted_by_test_transport' else 'smtp_accepted'
        else:
            cfg=store.get('discord')
            selected=[x for x in events if x['category'] in cfg.get('events',[]) or x['event'] in cfg.get('events',[])]
            if not cfg.get('enabled') or not selected:state='cancelled'
            else:
                subject,body=render(selected,cfg.get('language','de'),origin,store,'discord')
                notify.send_discord(store,subject+'\n'+body);state='discord_accepted'
        with store.db() as db:db.execute('UPDATE notification_outbox SET state=?,error_class=NULL WHERE id=?',(state,record['id']))
    except Exception as exc:
        attempts=record['attempts']+1
        with store.db() as db:db.execute('UPDATE notification_outbox SET state=?,next_at=?,error_class=? WHERE id=?',
            ('failed' if attempts>=3 else 'queued',time.time()+15*4**(attempts-1),type(exc).__name__,record['id']))
        store.event('email' if record['channel']=='email' else 'discord','notification_delivery_failed',record['user_id'],{'outbox_id':record['id'],'attempt':attempts,'error_class':type(exc).__name__})
    return True

def recover_inflight(store):
    # A process interruption after transmission has an uncertain outcome. Avoid blind duplicate delivery.
    with store.db() as db:db.execute("UPDATE notification_outbox SET state='delivery_uncertain' WHERE state='sending'")

def update_status(store,status):
    cfg=store.get('discord')
    if not cfg.get('enabled') or 'status' not in cfg.get('events',[]):return
    language=cfg.get('language','de');de=language=='de'
    running=status.get('container_status')=='running';players=status.get('players_online')
    server=store.get('server')
    uptime='—'
    if running and status.get('started_at'):
        started=datetime.fromisoformat(status['started_at'].replace('Z','+00:00')).timestamp()
        seconds=max(0,int(time.time()-started));uptime=str(seconds//3600)+'h '+str(seconds%3600//60)+'m'
    text='MCJ Manager\n'+('Online' if running else 'Offline')+' · '+server['version']+' · '+server['loader']+'\n'
    text+=('Spieler: ' if de else 'Players: ')+(str(players) if players is not None else ('unbekannt' if de else 'unknown'))
    text+=' · '+('Laufzeit: ' if de else 'Uptime: ')+uptime
    notify.send_discord(store,text,status=True)

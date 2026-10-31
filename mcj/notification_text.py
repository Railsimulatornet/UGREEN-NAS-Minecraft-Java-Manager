"""Human-readable notifications from explicitly selected, bounded event fields."""
from datetime import datetime
import json
import re
import uuid
from zoneinfo import ZoneInfo

MESSAGES = {
 'folder_mod_maintenance_queued': ('Neue Dateien aus deinem Mod-Ordner sind zur Installation vorgemerkt. Nach fünf Minuten ohne Spieler folgen Sicherung und getrennter Servertest. Andere vorgemerkte Änderungen bleiben erhalten.', 'New files from your mod folder are queued for installation. After five minutes without players, a backup and separate server test run first. Other pending changes are retained.'),
 'folder_mod_dependencies_failed': ('Die neuen Ordner-Mods passen noch nicht zusammen. Prüfe unter Mods die fehlenden Abhängigkeiten. Deine aktive Welt und installierten Mods bleiben unverändert.', 'The new folder mods do not work together yet. Check missing dependencies under Mods. Your active world and installed mods remain unchanged.'),
 'backup_verified': ('Dein Backup wurde erstellt und das Archiv geprüft. Unter Backups kannst du die Wiederherstellung in einer getrennten Testumgebung prüfen. Deine aktive Welt bleibt dabei unverändert.', 'Your backup was created and its archive verified. Under Backups, you can test restoring it in a separate test environment. Your active world stays unchanged during that test.'),
 'backup_failed': ('Das Backup konnte nicht erstellt werden. Öffne im Manager Backups und prüfe die Fehlermeldung, bevor du dich auf diese Sicherung verlässt.', 'The backup could not be created. Open Backups in the manager and check the error before relying on this backup.'),
 'backup_restored': ('Das ausgewählte Backup wurde wiederhergestellt.', 'The selected backup was restored.'),
 'restore_test_passed': ('Der Wiederherstellungstest war erfolgreich. Das Backup wurde in einer getrennten Testumgebung geprüft; deine aktive Welt wurde dabei nicht ersetzt.', 'The restore test succeeded in a separate test environment. Your active world was not replaced.'),
 'restore_test_failed': ('Der Wiederherstellungstest ist fehlgeschlagen. Deine aktive Welt wurde durch diesen Test nicht ersetzt. Prüfe die Details unter Backups.', 'The restore test failed. This test did not replace your active world. Check the details under Backups.'),
 'backup_retention_failed': ('Alte Backups konnten nicht wie vorgesehen bereinigt werden. Prüfe den freien Speicher und die Meldung unter Ereignisse.', 'Old backups could not be cleaned up as planned. Check free space and the message under Events.'),
 'version_applied': ('Die ausgewählte Serverversion wurde übernommen.', 'The selected server version was applied.'),
 'mods_applied': ('Die geplanten Mod-Änderungen wurden übernommen.', 'The planned mod changes were applied.'),
 'settings_applied': ('Die freigegebenen Server-Einstellungen wurden nach Sicherung und getrenntem Starttest übernommen. Die aktuellen Werte findest du unter Server-Einstellungen.', 'The approved server settings were applied after a backup and a separate startup test. Find the current values under Server settings.'),
 'combined_applied': ('Die freigegebenen Server- und Modänderungen wurden gemeinsam nach Sicherung und getrenntem Starttest übernommen. Prüfe die aktuellen Einstellungen und installierten Mods im Manager.', 'The approved server and mod changes were applied together after a backup and a separate startup test. Review the current settings and installed mods in the manager.'),
 'world_applied': ('Die vorbereitete Spielwelt wurde nach Sicherung und getrenntem Starttest als aktive Spielwelt übernommen.', 'The prepared world was applied as the active game world after a backup and a separate startup test.'),
 'version_test_passed': ('Der ausgewählte Serverstand hat den isolierten Starttest bestanden. Die Übernahme ist ein eigener Schritt; der Test allein ändert deinen laufenden Server nicht.', 'The selected server setup passed its isolated startup test. Applying it is a separate step; the test alone does not change your running server.'),
 'version_test_failed': ('Der ausgewählte Serverstand hat den isolierten Test nicht bestanden. Prüfe den Testbericht unter Wartung, bevor du die Änderung erneut versuchst.', 'The selected server setup failed its isolated test. Review the report under Maintenance before trying the change again.'),
 'change_rolled_back': ('Die Änderung konnte nicht erfolgreich abgeschlossen werden. Der Manager hat den vorherigen Stand wiederhergestellt. Die Einzelheiten stehen unter Wartung.', 'The change could not be completed successfully. The manager restored the previous setup. See Maintenance for details.'),
 'automatic_mod_maintenance_queued': ('Die automatische Mod-Wartung ist vorgemerkt. Sie wartet auf die vorgesehenen Bedingungen und prüft die Änderungen vor der Übernahme.', 'Automatic mod maintenance is queued. It waits for the required conditions and tests changes before applying them.'),
 'automatic_mod_staging_failed': ('Die automatische Vorbereitung der Mod-Updates ist fehlgeschlagen. Öffne Wartung, um die Ursache zu prüfen.', 'Preparing automatic mod updates failed. Open Maintenance to check the cause.'),
 'job_approved': ('Der Wartungsauftrag wurde freigegeben. Den weiteren Fortschritt findest du unter Wartung.', 'The maintenance job was approved. Follow its progress under Maintenance.'),
 'job_cancelled': ('Der vorgemerkte Wartungsauftrag wurde verworfen.', 'The queued maintenance job was cancelled.'),
 'duplicate_jobs_cancelled': ('Doppelte Wartungsaufträge wurden entfernt, damit dieselbe Änderung nicht mehrfach ausgeführt wird.', 'Duplicate maintenance jobs were removed so the same change is not run repeatedly.'),
 'version_plan_created': ('Eine neue Versionsauswahl wurde vorbereitet. Prüfe die Konfiguration und wähle selbst, wann du sie übernehmen möchtest.', 'A new version selection was prepared. Review the configuration and choose when to apply it.'),
 'source_list_updated': ('Die Liste deiner Mod- und Modpack-Quellen wurde gespeichert.', 'Your list of mod and modpack sources was saved.'),
 'source_staged': ('Dateien aus einer Mod-Quelle wurden zur Übernahme vorgemerkt. Auf dem laufenden Server sind sie dadurch noch nicht aktiviert.', 'Files from a mod source are ready for review. They are not active on the running server yet.'),
 'source_files_staged': ('Mod-Dateien wurden zur Übernahme vorgemerkt. Prüfe die Auswahl unter Gesammelte Änderungen.', 'Mod files are ready for review. Check your selection under Collected changes.'),
 'pack_staged': ('Ein Modpack wurde zur Übernahme vorgemerkt. Prüfe die Auswahl und den geplanten Serverstand vor der Installation.', 'A modpack is ready for review. Check your selection and the planned server setup before installing it.'),
 'pack_properties_selected': ('Die Auswahl der Servereinstellungen aus dem Modpack wurde geändert. Die Übernahme erfolgt über den Wartungsablauf.', 'The selection of server settings from the modpack changed. They are applied through the maintenance workflow.'),
 'jar_staged': ('Eine Mod-Datei wurde hochgeladen und bereitgestellt. Sie läuft erst nach der freigegebenen Installation auf dem Server.', 'A mod file was uploaded and staged. It runs on the server only after the installation is approved and completed.'),
 'manual_file_staged': ('Die ausgewählte Mod-Datei wurde bereitgestellt. Prüfe die gesammelten Änderungen vor der Installation.', 'The selected mod file was staged. Review the collected changes before installation.'),
 'manual_file_rejected': ('Diese Datei konnte nicht als Server-Mod bereitgestellt werden. Sie wurde nicht installiert. Lade eine vollständige JAR für deine Minecraft- und Modloader-Version herunter und lege sie direkt im Mod-Ordner ab.', 'This file could not be prepared as a server mod. It was not installed. Download a complete JAR for your Minecraft and mod-loader versions and place it directly in the mods folder.'),
 'mod_removal_staged': ('Die Deinstallation der Mod wurde vorgemerkt. Sie wird erst mit der bestätigten Wartung übernommen.', 'The mod is selected for removal. It will be removed only when the approved maintenance job runs.'),
 'mod_removal_cancelled': ('Die vorgemerkte Deinstallation der Mod wurde zurückgenommen.', 'The pending mod uninstall was cancelled.'),
 'mod_update_cancelled': ('Das vorgemerkte Mod-Update wurde zurückgenommen.', 'The pending mod update was cancelled.'),
 'mod_update_staged': ('Ein Mod-Update wurde vorbereitet. Es wird erst nach Sicherung, Prüfung und freigegebener Übernahme installiert.', 'A mod update was prepared. It is installed only after backup, testing and approved application.'),
 'mod_version_staged': ('Eine andere Mod-Version wurde vorgemerkt. Prüfe sie unter Gesammelte Änderungen.', 'A different mod version is ready for review. Check it under Collected changes.'),
 'mods_uninstalled': ('Die ausgewählten Mods wurden deinstalliert.', 'The selected mods were uninstalled.'),
 'client_pack_created': ('Ein neues Clientpaket für deine Mitspieler wurde erstellt. Du findest es unter Mods → Client-Modpack.', 'A new client pack for your players was created. Find it under Mods → Client modpack.'),
 'client_pack_deleted': ('Ausgewählte Clientpakete wurden gelöscht. Die Mods auf dem laufenden Server werden dadurch nicht deinstalliert.', 'Selected client packs were deleted. This does not uninstall mods from the running server.'),
 'client_pack_shared': ('Ein Download-Link für ein Clientpaket wurde erstellt. Du kannst ihn unter Mods → Client-Modpack verwalten.', 'A client-pack download link was created. Manage it under Mods → Client modpack.'),
 'client_pack_link_revoked': ('Ein Download-Link für ein Clientpaket wurde zurückgezogen und kann nicht mehr verwendet werden.', 'A client-pack download link was revoked and can no longer be used.'),
 'client_mod_side_changed': ('Die Zuordnung einer Mod zum Clientpaket wurde geändert. Erstelle das Clientpaket erneut, wenn die neue Zuordnung enthalten sein soll.', 'A mod’s client-pack assignment changed. Rebuild the client pack to include that assignment.'),
 'loader_metadata_failed': ('Die Modloader-Angaben konnten nicht aktualisiert werden. Prüfe die Internetverbindung des NAS und die Meldung unter Ereignisse.', 'Mod-loader information could not be refreshed. Check the NAS internet connection and the message under Events.'),
 'server_start': ('Der Start des Minecraft-Servers wurde ausgeführt. Den aktuellen Zustand siehst du in der Übersicht.', 'The Minecraft server start was carried out. Check its current state in Overview.'),
 'server_stop': ('Der Minecraft-Server wurde gestoppt.', 'The Minecraft server was stopped.'),
 'server_restart': ('Der Neustart des Minecraft-Servers wurde ausgeführt. Den aktuellen Zustand siehst du in der Übersicht.', 'The Minecraft server restart was carried out. Check its current state in Overview.'),
 'stable_versions_checked': ('Die Suche nach stabilen Minecraft-Versionen ist abgeschlossen. Die Versionsliste ist aktualisiert; deine installierte Version wurde dadurch nicht gewechselt.', 'The search for stable Minecraft versions is complete. The version list was refreshed; your installed version was not changed.'),
 'world_import_staged': ('Eine Welt wurde für den Import bereitgestellt. Deine aktive Welt wird erst nach deiner bestätigten Übernahme gewechselt.', 'A world was staged for import. Your active world changes only after your approved application.'),
 'world_deleted': ('Die ausgewählte Welt wurde gelöscht.', 'The selected world was deleted.'),
 'world_exported': ('Der Export der ausgewählten Welt ist fertig.', 'The selected world’s export is ready.'),
 'game_rule_changed': ('Eine Spielregel wurde geändert. Die neue Regel gilt für die aktive Welt.', 'A game rule changed. The new rule applies to the active world.'),
 'console_command': ('Ein Minecraft-Befehl wurde über die Manager-Konsole gesendet. Den Befehl und die Einzelheiten findest du im geschützten Ereignisverlauf.', 'A Minecraft command was sent through the manager console. See the protected event history for the command and details.'),
 'chat_sent': ('Eine Nachricht wurde über den Manager an den Minecraft-Chat gesendet.', 'A message was sent to Minecraft chat through the manager.'),
 'runtime_cleanup_completed': ('Die Bereinigung nicht mehr benötigter Laufzeitdateien ist abgeschlossen.', 'Cleanup of unused runtime files is complete.'),
 'runtime_files_deleted': ('Die ausgewählten lokalen Laufzeitdateien wurden gelöscht.', 'The selected local runtime files were deleted.'),
 'minecraft_permissions_updated': ('Die zusätzlichen Minecraft-Berechtigungen für Spielergruppen wurden gespeichert. Sie vergeben weder Minecraft-OP noch Zugang zur Weboberfläche.', 'Additional Minecraft permissions for player groups were saved. They grant neither Minecraft OP nor web-interface access.'),
 'player_presence_unavailable': ('Die aktuellen Spielerinformationen konnten nicht abgefragt werden. Die Spielerzahl ist deshalb vorübergehend nicht verlässlich verfügbar.', 'Current player information could not be retrieved. The player count is temporarily unavailable or unreliable.'),
 'request_failed': ('Eine Anfrage an den Manager ist fehlgeschlagen. Prüfe im Ereignisverlauf, welche Aktion betroffen war.', 'A request to the manager failed. Check the event history to see which action was affected.'),
 'worker_error': ('Ein Hintergrundschritt ist fehlgeschlagen. Öffne Ereignisse und Wartung, um den betroffenen Vorgang zu prüfen.', 'A background step failed. Open Events and Maintenance to inspect the affected operation.'),
 'web_access_changed': ('Die Freigabe der Weboberfläche für externe Zugriffe wurde geändert. Prüfe die aktuelle Auswahl unter Infrastruktur und Freigabe.', 'External access to the web interface changed. Review the selection under Infrastructure and access.'),
 'game_access_changed': ('Die Freigabe des Minecraft-Zugangs wurde geändert. Prüfe die aktuelle Auswahl unter Infrastruktur und Freigabe.', 'Minecraft access settings changed. Review the selection under Infrastructure and access.'),
 'web_address_activated': ('Die neue Webadresse des Managers wurde bestätigt und aktiviert.', 'The manager’s new web address was confirmed and activated.'),
 'diagnostics_downloaded': ('Ein Diagnosepaket wurde über den Manager heruntergeladen.', 'A diagnostic package was downloaded through the manager.'),
 'event_cleanup_policy_updated': ('Die Aufbewahrungseinstellungen für den Ereignisverlauf wurden geändert.', 'Event-history retention settings changed.'),
 'user_created': ('Ein neues Konto für die Weboberfläche wurde angelegt.', 'A new account for the web interface was created.'),
 'user_updated': ('Ein Konto für die Weboberfläche wurde geändert.', 'An account for the web interface changed.'),
 'profile_updated': ('Die Einstellungen eines Webkontos wurden gespeichert.', 'A web account’s preferences were saved.'),
 'session_policy_updated': ('Die Gültigkeitsdauer für Anmeldungen wurde geändert.', 'The sign-in session lifetime changed.'),
 'login_success': ('Eine Anmeldung am Manager war erfolgreich.', 'Someone signed in to the manager successfully.'),
 'login_failed': ('Eine Anmeldung am Manager ist fehlgeschlagen. Das allein bedeutet nicht, dass jemand Zugriff erhalten hat.', 'A manager sign-in attempt failed. This alone does not mean anyone gained access.'),
 'logout': ('Ein Webkonto wurde vom Manager abgemeldet.', 'A web account signed out of the manager.'),
 'password_verified': ('Das Passwort für die Anmeldung wurde bestätigt. Die vollständige Anmeldung kann noch einen Sicherheitscode erfordern.', 'The sign-in password was verified. A security code may still be required to complete sign-in.'),
 'factor_failed': ('Ein Sicherheitscode wurde abgewiesen. Verwende bei deiner eigenen Anmeldung den neuesten E-Mail-Code oder den aktuellen Code deiner Authenticator-App. Prüfe bei der App auch die automatische Uhrzeit.', 'A security code was rejected. For your own sign-in, use the latest email code or the current code from your authenticator app. For the app, also check that automatic time is enabled.'),
 'factor_configured': ('Die zusätzliche Absicherung eines Webkontos wurde eingerichtet.', 'An additional sign-in factor was configured for a web account.'),
 'password_changed': ('Das Passwort eines Webkontos wurde geändert. Wenn du diese Änderung nicht veranlasst hast, prüfe dein Konto sofort.', 'A web account’s password changed. If you did not request this, check your account immediately.'),
 'password_reset_requested': ('Eine Passwortwiederherstellung wurde angefordert. Das Passwort wurde dadurch noch nicht geändert.', 'A password reset was requested. This has not changed the password.'),
 'password_reset_complete': ('Ein Passwort wurde über die Wiederherstellung neu gesetzt. Wenn du das nicht veranlasst hast, prüfe das betroffene Konto sofort.', 'A password was reset through recovery. If you did not request this, check the affected account immediately.'),
 'password_reset_link_rejected': ('Ein Link zur Passwortwiederherstellung wurde abgewiesen. Verwende bei deinem eigenen Versuch einen neuen, noch gültigen Link.', 'A password-reset link was rejected. For your own attempt, use a new link that is still valid.'),
 'factor_recovery_requested': ('Die Wiederherstellung der Zweifaktor-Anmeldung wurde angefordert. Sie ist damit noch nicht abgeschlossen.', 'Two-factor sign-in recovery was requested. Recovery is not complete yet.'),
 'factor_recovery_completed': ('Die Wiederherstellung der Zweifaktor-Anmeldung wurde bestätigt.', 'Two-factor sign-in recovery was confirmed.'),
 'factor_recovery_failed': ('Die Wiederherstellung der Zweifaktor-Anmeldung wurde abgewiesen. Prüfe die Angaben im geschützten Ereignisverlauf.', 'Two-factor sign-in recovery was rejected. Check the protected event history.'),
 'factor_recovery_delivery_failed': ('Die E-Mail für die Wiederherstellung der Zweifaktor-Anmeldung konnte nicht versendet werden. Prüfe die Maileinstellungen.', 'The two-factor recovery email could not be sent. Check outgoing email settings.'),
 'recovery_code_used': ('Bei einer Anmeldung wurde ein einmaliger Wiederherstellungscode verwendet. Dieser Code ist jetzt verbraucht.', 'A one-time recovery code was used to sign in. That code can no longer be used.'),
 'recovery_codes_regenerated': ('Neue Wiederherstellungscodes wurden erstellt. Die vorherigen Codes sind dadurch ungültig.', 'New recovery codes were created. The previous codes are no longer valid.'),
 'session_reauthenticated': ('Eine erneute Sicherheitsbestätigung für die aktuelle Sitzung war erfolgreich.', 'A renewed security confirmation for the current session succeeded.'),
 'sessions_revoked': ('Gespeicherte Anmeldesitzungen wurden beendet. Betroffene Geräte müssen sich erneut anmelden.', 'Saved sign-in sessions were ended. Affected devices must sign in again.'),
 'greeting_sent': ('Die persönliche Begrüßung wurde an Minecraft übergeben.', 'The personal greeting was handed to Minecraft.'),
 'greeting_failed': ('Die persönliche Begrüßung konnte nicht an Minecraft übergeben werden.', 'The personal greeting could not be handed to Minecraft.'),
}

TITLES = {
 'player_op': ('Minecraft-Operatorrechte geändert','Minecraft operator permissions changed'),
 'player_whitelist': ('Minecraft-Spielerfreigabe geändert','Minecraft player access changed'),
 'player_kick': ('Spieler vom Server getrennt','Player removed from server'),
 'game_access_changed': ('Minecraft-Zugang geändert','Minecraft access changed'),
 'web_access_changed': ('Webzugang geändert','Web access changed'),
 'web_address_activated': ('Neue Webadresse aktiviert','New web address activated'),
 'logout': ('Vom Manager abgemeldet','Signed out of manager'),
 'password_reset_link_rejected': ('Passwortlink abgewiesen','Password-reset link rejected'),
 'password_verified': ('Anmeldepasswort bestätigt','Sign-in password verified'),
 'profile_updated': ('Kontoeinstellungen gespeichert','Account preferences saved'),
 'recovery_code_used': ('Wiederherstellungscode verwendet','Recovery code used'),
 'recovery_codes_regenerated': ('Wiederherstellungscodes erneuert','Recovery codes regenerated'),
 'restore_test_failed': ('Wiederherstellungstest fehlgeschlagen','Restore test failed'),
 'session_reauthenticated': ('Sitzung erneut bestätigt','Session reconfirmed'),
 'sessions_revoked': ('Anmeldesitzungen beendet','Sign-in sessions ended'),
 'client_pack_deleted': ('Clientpakete gelöscht','Client packs deleted'),
 'client_pack_created': ('Clientpaket erstellt','Client pack created'),
 'client_pack_shared': ('Clientpaket-Link erstellt','Client-pack link created'),
 'client_pack_link_revoked': ('Clientpaket-Link zurückgezogen','Client-pack link revoked'),
 'client_mod_side_changed': ('Clientpaket-Zuordnung geändert','Client-pack assignment changed'),
 'mod_desired_changed': ('Mod-Auswahl geändert','Mod selection changed'),
 'mod_removal_staged': ('Mod-Deinstallation vorgemerkt','Mod uninstall queued'),
 'mod_removal_cancelled': ('Mod-Deinstallation zurückgenommen','Mod uninstall cancelled'),
 'mod_update_cancelled': ('Mod-Update zurückgenommen','Mod update cancelled'),
 'mod_update_staged': ('Mod-Update vorbereitet','Mod update prepared'),
 'mod_version_staged': ('Mod-Version vorgemerkt','Mod version selected'),
 'mods_uninstalled': ('Mods deinstalliert','Mods uninstalled'),
 'jar_staged': ('Mod-Datei bereitgestellt','Mod file staged'),
 'manual_file_staged': ('Mod-Datei bereitgestellt','Mod file staged'),
 'manual_file_rejected': ('Mod-Datei abgewiesen','Mod file rejected'),
 'loader_metadata_failed': ('Modloader-Angaben nicht erreichbar','Mod-loader information unavailable'),
 'stable_versions_checked': ('Minecraft-Versionsliste aktualisiert','Minecraft version list refreshed'),
 'world_deleted': ('Welt gelöscht','World deleted'),
 'world_exported': ('Weltexport fertig','World export ready'),
 'world_applied': ('Spielwelt gewechselt','Game world switched'),
 'settings_applied': ('Server-Einstellungen übernommen','Server settings applied'),
 'combined_applied': ('Server- und Modänderungen übernommen','Server and mod changes applied'),
 'game_rule_changed': ('Spielregel geändert','Game rule changed'),
 'console_command': ('Minecraft-Befehl gesendet','Minecraft command sent'),
 'runtime_cleanup_completed': ('Laufzeitdateien bereinigt','Runtime files cleaned up'),
 'runtime_files_deleted': ('Lokale Laufzeitdateien gelöscht','Local runtime files deleted'),
 'player_presence_unavailable': ('Spielerstatus nicht verfügbar','Player status unavailable'),
 'user_created': ('Webkonto angelegt','Web account created'),
 'session_policy_updated': ('Anmeldedauer geändert','Sign-in lifetime changed'),
 'diagnostics_downloaded': ('Diagnosepaket heruntergeladen','Diagnostic package downloaded'),
 'event_cleanup_policy_updated': ('Ereignisaufbewahrung geändert','Event retention changed'),
 'greeting_sent': ('Begrüßung gesendet','Greeting sent'),
 'greeting_failed': ('Begrüßung nicht gesendet','Greeting not sent'),
 'job_approved': ('Wartung freigegeben','Maintenance approved'),
 'job_cancelled': ('Wartung verworfen','Maintenance cancelled'),
 'duplicate_jobs_cancelled': ('Doppelte Wartung entfernt','Duplicate maintenance removed'),
 'version_plan_created': ('Versionsauswahl vorbereitet','Version selection prepared'),
}

JOBS = {
 'backup': ('Backup erstellen','Create a backup'),
 'mod_check': ('Mod-Updates prüfen','Check mod updates'),
 'curseforge_install': ('CurseForge-Mod installieren','Install a CurseForge mod'),
 'client_pack_build': ('Clientpaket erstellen','Build a client pack'),
 'mod_version': ('Mod-Version vorbereiten','Prepare a mod version'),
 'source_check': ('Mod-Quelle prüfen','Check a mod source'),
 'source_stage': ('Dateien aus Mod-Quelle vorbereiten','Prepare mod-source files'),
 'restore_test': ('Wiederherstellung testen','Test a backup restore'),
 'version_test': ('Serverversion isoliert testen','Test a server version in isolation'),
 'version_apply': ('Serverversion übernehmen','Apply a server version'),
 'world_change': ('Spielwelt wechseln','Switch the game world'),
 'world_delete': ('Spielwelt löschen','Delete a game world'),
 'world_export': ('Spielwelt exportieren','Export a game world'),
 'server_settings': ('Server-Einstellungen übernehmen','Apply server settings'),
 'apply_mods': ('Mod-Änderungen übernehmen','Apply mod changes'),
 'restore': ('Backup wiederherstellen','Restore a backup'),
 'server': ('Minecraft-Server steuern','Control the Minecraft server'),
}
ROLES = {'visitor':('Besucher','Visitor'),'player':('Spieler','Player'),
         'moderator':('Moderator','Moderator'),'administrator':('Administrator','Administrator')}
SERVER_JOBS = {
 'start': ('Minecraft-Server starten','Start Minecraft server'),
 'stop': ('Minecraft-Server stoppen','Stop Minecraft server'),
 'restart': ('Minecraft-Server neu starten','Restart Minecraft server'),
}

def data_of(event):
    value=event.get('data',{})
    if isinstance(value,str):
        try:value=json.loads(value)
        except (ValueError,TypeError):value={}
    return value if isinstance(value,dict) else {}

def count(value):
    return value if type(value) is int and 0<=value<=1_000_000_000 else None

def player_name(data,store):
    name=data.get('name')
    if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_]{1,16}',name):return name
    identifier=data.get('uuid')
    if not store or not isinstance(identifier,str):return None
    try:
        if str(uuid.UUID(identifier))!=identifier:return None
    except ValueError:return None
    with store.db() as db:row=db.execute('SELECT name FROM players WHERE uuid=?',(identifier,)).fetchone()
    if row and re.fullmatch(r'[A-Za-z0-9_]{1,16}',row['name']):return row['name']
    return None

def mod_name(data,store):
    identifier=data.get('id')
    if not store or not isinstance(identifier,str) or len(identifier)>100:return None
    with store.db() as db:row=db.execute('SELECT metadata,filename FROM mods WHERE id=?',(identifier,)).fetchone()
    if not row:return None
    try:value=json.loads(row['metadata'])['mods'][0].get('name')
    except (ValueError,KeyError,IndexError,TypeError):value=None
    for value in (value,row['filename']):
        if isinstance(value,str) and re.fullmatch(r"[\w .():+'-]{1,120}",value):return value
    return None

def account_name(event,data,store):
    if not store:return None
    from .notification_policy import account_subject
    identifier=account_subject(event)
    if type(identifier) is not int or identifier<1:return None
    with store.db() as db:row=db.execute('SELECT username FROM users WHERE id=?',(identifier,)).fetchone()
    if row and re.fullmatch(r'[\w .-]{1,64}',row['username']):return row['username']
    return None

def describe(event,language,labels,store=None):
    i=0 if language=='de' else 1;de=i==0
    kind=event['event'];data=data_of(event)
    title=TITLES.get(kind,labels.get(kind,('Meldung im Manager','Manager notification')))[i]
    body=MESSAGES.get(kind,('', ''))[i]
    if kind in {'world_import_staged','world_exported','world_deleted','world_applied'}:
        runtime=data.get('runtime')
        name=runtime.get('world') if kind=='world_applied' and isinstance(runtime,dict) else data.get('name')
        if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,60}',name):
            title+=': '+name
            body=('Welt „'+name+'“: ' if de else 'World “'+name+'”: ')+body
    if kind in {'player_login','player_logout','player_role','player_ban','player_unban','player_kick','player_op','player_whitelist','greeting_sent','greeting_failed'}:
        name=player_name(data,store) or ('Ein Spieler' if de else 'A player')
        if kind=='player_login':title,body=(('Spieler beigetreten',name+' ist dem Server beigetreten.') if de else ('Player joined',name+' joined the server.'))
        elif kind=='player_logout':title,body=(('Spieler hat den Server verlassen',name+' hat den Server verlassen.') if de else ('Player left',name+' left the server.'))
        elif kind=='player_role':
            role=ROLES.get(data.get('role')) if isinstance(data.get('role'),str) else None
            body=(name+' hat jetzt die Spielergruppe „'+role[i]+'“.' if de else name+' now belongs to the '+role[i]+' player group.') if role else (name+': Die Spielergruppe wurde geändert.' if de else name+': The player group changed.')
        elif kind in {'player_ban','player_unban','player_kick'}:
            body=name+({'player_ban':(' wurde auf dem Server gesperrt.',' was banned from the server.'),'player_unban':(' darf nach Aufhebung der Sperre wieder auf den Server.',' was unbanned from the server.'),'player_kick':(' wurde vom Server getrennt.',' was removed from the server.')}[kind][i])
        elif kind in {'player_op','player_whitelist'}:
            enabled=data.get('enabled')
            if type(enabled) is not bool:body=name+(': Die Minecraft-Berechtigungen wurden geändert.' if de else ': Minecraft permissions changed.')
            elif kind=='player_op':body=name+ ((' hat Minecraft-Operatorrechte erhalten.' if enabled is True else ' hat keine Minecraft-Operatorrechte mehr.') if de else (' was granted Minecraft operator permissions.' if enabled is True else ' no longer has Minecraft operator permissions.'))
            else:body=name+ ((' wurde für den Minecraft-Zugang freigegeben.' if enabled is True else ' ist nicht mehr für den Minecraft-Zugang freigegeben.') if de else (' was approved for Minecraft access.' if enabled is True else ' is no longer approved for Minecraft access.'))
        else:body=name+': '+body
        if player_name(data,store):title+=': '+name
    if kind in {'job_queued','job_approved','job_cancelled','job_failed'}:
        job_kind=data.get('kind') if isinstance(data.get('kind'),str) else None
        identifier=data.get('job',data.get('id'))
        server_operation=data.get('operation')
        if (job_kind not in JOBS or job_kind=='server') and store and isinstance(identifier,str) and re.fullmatch(r'[a-f0-9]{32}',identifier):
            with store.db() as db:row=db.execute('SELECT kind,payload FROM jobs WHERE id=?',(identifier,)).fetchone()
            if row:
                job_kind=row['kind']
                if job_kind=='server':
                    try:payload=json.loads(row['payload'])
                    except (ValueError,TypeError):payload={}
                    server_operation=payload.get('operation') if isinstance(payload,dict) else None
        operation=JOBS.get(job_kind,('Wartungsauftrag','Maintenance job'))[i]
        if job_kind=='server' and isinstance(server_operation,str) and server_operation in SERVER_JOBS:
            operation=SERVER_JOBS[server_operation][i]
        state_title={
            'job_queued':('Vorgemerkt: ','Queued: '),
            'job_failed':('Fehlgeschlagen: ','Failed: '),
            'job_approved':('Freigegeben: ','Approved: '),
            'job_cancelled':('Verworfen: ','Cancelled: '),
        }[kind][i]
        title=state_title+operation
        if kind=='job_queued':
            body=('Der Auftrag „'+operation+'“ ist vorgemerkt. Den Fortschritt und die Bedingungen für den Start findest du unter Wartung.' if de else 'The job “'+operation+'” is queued. Find its progress and start conditions under Maintenance.')
        elif kind=='job_failed':
            body=('Der Auftrag „'+operation+'“ ist fehlgeschlagen. Öffne Wartung und lies die Fehlerdetails, bevor du ihn erneut startest.' if de else 'The job “'+operation+'” failed. Open Maintenance and read the error details before trying again.')
        elif kind=='job_approved':body=('Der Auftrag „'+operation+'“ wurde freigegeben. Den Fortschritt findest du unter Wartung.' if de else 'The job “'+operation+'” was approved. Follow its progress under Maintenance.')
        else:body=('Der Auftrag „'+operation+'“ wurde verworfen.' if de else 'The job “'+operation+'” was cancelled.')
    if kind=='mod_desired_changed':
        name=mod_name(data,store) or ('Die Mod' if de else 'The mod')
        choice=('aktiviert' if data.get('enabled') is True else 'deaktiviert') if de else ('enabled' if data.get('enabled') is True else 'disabled')
        body=(name+' soll '+choice+' werden. Das ist vorgemerkt; der laufende Server ändert sich erst mit der bestätigten Übernahme unter Gesammelte Änderungen.' if de else name+' is selected to be '+choice+'. This is a pending change; the running server changes only after approved application under Collected changes.')
        if type(data.get('enabled')) is not bool:body=(name+': Die vorgemerkte Aktivierung wurde geändert. Prüfe die Auswahl unter Gesammelte Änderungen.' if de else name+': The pending activation changed. Review Collected changes.')
    elif kind=='client_pack_deleted':
        ids=data.get('ids');number=len(ids) if isinstance(ids,list) else None
        if number is not None:body=(str(number)+' Clientpaket'+(' wurde' if number==1 else 'e wurden')+' gelöscht. Die Mods auf dem laufenden Server bleiben installiert.' if de else str(number)+' client pack'+(' was' if number==1 else 's were')+' deleted. Mods on the running server remain installed.')
        revoked=count(data.get('revoked_links'))
        if revoked:body+=(' '+str(revoked)+(' zugehöriger Download-Link wurde ungültig.' if revoked==1 else ' zugehörige Download-Links wurden ungültig.') if de else ' '+str(revoked)+(' associated download link was invalidated.' if revoked==1 else ' associated download links were invalidated.'))
    elif kind=='update_check_completed':
        title=('Modprüfung abgeschlossen' if de else 'Mod check complete')
        checked=count(data.get('checked'));updates=count(data.get('updates'));failed=count(data.get('failed'));unknown=count(data.get('unresolved'))
        body=('Die Suche nach Mod-Updates ist abgeschlossen.' if de else 'The search for mod updates is complete.')
        if checked==0:body+=(' Es waren keine Mods für diese Prüfung vorhanden.' if de else ' There were no mods for this check.')
        elif checked is not None:body+=(' '+str(checked)+(' Mod wurde berücksichtigt.' if checked==1 else ' Mods wurden berücksichtigt.') if de else ' '+str(checked)+(' mod was considered.' if checked==1 else ' mods were considered.'))
        if updates is not None and checked!=0:
            incomplete=bool(failed or unknown)
            none=('Die Prüfung war unvollständig. Bisher wurden keine Updates gefunden.' if incomplete else 'Es wurden keine Updates gefunden.') if de else ('The check was incomplete. No updates have been found so far.' if incomplete else 'No updates were found.')
            body+=(' '+(none if updates==0 else 'Ein Update ist verfügbar.' if updates==1 else str(updates)+' Updates sind verfügbar.') if de else ' '+(none if updates==0 else 'One update is available.' if updates==1 else str(updates)+' updates are available.'))
        if failed:body+=(' '+str(failed)+(' Mod konnte nicht geprüft werden.' if failed==1 else ' Mods konnten nicht geprüft werden.') if de else ' '+str(failed)+(' mod could not be checked.' if failed==1 else ' mods could not be checked.'))
        if unknown:body+=(' Bei '+str(unknown)+(' Mod blieb das Ergebnis offen.' if unknown==1 else ' Mods blieb das Ergebnis offen.') if de else ' The result remains unresolved for '+str(unknown)+(' mod.' if unknown==1 else ' mods.'))
        body+=(' Die Ergebnisse stehen unter Mods. Updates werden über den Wartungsablauf übernommen.' if de else ' See Mods for the results. Updates are applied through the maintenance workflow.')
    elif kind=='stable_versions_checked':
        version=data.get('latest_stable')
        if isinstance(version,str) and re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+_-]{0,59}',version):body+=(' Neueste stabile Version: ' if de else ' Latest stable version: ')+version+'.'
    elif kind=='player_moderation':
        name=player_name(data,store) or ('Ein Moderator' if de else 'A moderator')
        action={'kick':('einen Spieler zu trennen','remove a player'),'announce':('eine Chatansage zu senden','send a chat announcement'),'time':('die Tageszeit zu ändern','change the time of day'),'weather':('das Wetter zu ändern','change the weather')}.get(data.get('action'))
        title=('Spielaktion freigegeben' if de else 'In-game action authorised')
        body=(name+' hat die Freigabe erhalten, '+action[i]+'. Das bestätigt die Berechtigung, noch nicht die Ausführung.' if de else name+' was authorised to '+action[i]+'. This confirms permission, not execution.') if action else ('Eine Spielaktion wurde autorisiert. Einzelheiten stehen im Ereignisverlauf.' if de else 'An in-game action was authorised. See the event history for details.')
    if kind=='manual_file_rejected':
        reason=data.get('reason')
        explanations={
            'jar_invalid':('Die Datei ist keine gültige, vollständige Mod-JAR. Sie wurde nicht installiert. Lade die passende Originaldatei vom Mod-Anbieter erneut herunter.', 'The file is not a valid, complete mod JAR. It was not installed. Download the matching original file again from the mod provider.'),
            'jar_unsafe_path':('Die Mod-Datei enthält unzulässige Dateipfade und wurde nicht übernommen. Verwende eine unveränderte Originaldatei des Mod-Anbieters.', 'The mod archive contains unsafe file paths and was not accepted. Use an unmodified original file from the mod provider.'),
            'symlink':('Im Mod-Ordner liegt eine Dateiverknüpfung. Der Manager übernimmt nur echte JAR-Dateien. Kopiere die passende Originaldatei direkt in den Mod-Ordner.', 'The mods folder contains a file link. The manager accepts regular JAR files only. Copy the matching original file directly into the mods folder.'),
        }
        if isinstance(reason,str) and reason in explanations:body=explanations[reason][i]
        body+=(' Installierte Mods und aktive Welt wurden dabei nicht verändert.' if de else ' Installed mods and the active world were not changed by this rejection.')
    if kind in {'jar_staged','manual_file_staged','manual_file_rejected','mod_removal_staged','mod_removal_cancelled','mod_update_cancelled','mod_update_staged','mod_version_staged'}:
        name=mod_name(data,store)
        if not name and isinstance(data.get('filename'),str) and re.fullmatch(r"[\w .():+'-]{1,120}",data['filename']):name=data['filename']
        if name:body=name+': '+body;title+=': '+name
    if kind in {'folder_mod_maintenance_queued','folder_mod_dependencies_failed'}:
        names=[x for x in data.get('files',[]) if isinstance(x,str) and re.fullmatch(r'[A-Za-z0-9_.+() -]{1,160}\.jar',x)][:10]
        if names:body+=' '+('Dateien: ' if de else 'Files: ')+', '.join(names)+'.'
    if kind=='game_rule_changed':
        rule=data.get('key');enabled=data.get('enabled')
        if isinstance(rule,str) and re.fullmatch(r'[a-zA-Z0-9_:]{1,80}',rule) and type(enabled) is bool:
            body=(('Die Spielregel „'+rule+'“ ist jetzt '+('eingeschaltet.' if enabled else 'ausgeschaltet.')) if de else 'The game rule “'+rule+'” is now '+('enabled.' if enabled else 'disabled.'))
    if event.get('category') in {'auth','user'}:
        name=account_name(event,data,store)
        if name:title+=': '+name;body=(('Webkonto '+name+': ') if de else 'Web account '+name+': ')+body
    if not body:
        # Explain where to inspect an unfamiliar event without exposing internal keys.
        category=labels.get(event.get('category'),('Manager','Manager'))[i]
        body=(category+': '+title+'. Öffne im Manager den Bereich Ereignisse und prüfe den Eintrag zu diesem Zeitpunkt.' if de else category+': '+title+'. Open Events in the manager and check the entry at this time.')
    return title,body

def render(events,language,origin,labels,store=None,channel='email'):
    de=language=='de'
    entries=[]
    for event in events:
        title,body=describe(event,language,labels,store)
        stamp=datetime.fromtimestamp(event['at'],ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y, %H:%M %Z')
        entries.append((title,stamp+'\n'+title+'\n'+body))
    if len(entries)==1:subject='MCJ Manager – '+entries[0][0]
    else:subject='MCJ Manager – '+str(len(entries))+(' Meldungen zu deinem Server' if de else ' server notifications')
    footer=('Mehr dazu: Öffne im Manager den Bereich Ereignisse.' if de else 'More details: open Events in the manager.')
    if len(origin)<=250:footer+='\n'+origin
    blocks=[];limit=max(0,1850-len(subject)-len(footer)-100) if channel=='discord' else None
    for _,block in entries:
        if limit is not None and sum(len(x)+2 for x in blocks)+len(block)>limit:break
        blocks.append(block)
    remaining=len(entries)-len(blocks)
    if remaining:blocks.append((str(remaining)+' weitere Meldungen findest du im Manager.' if de else str(remaining)+' more notifications are available in the manager.'))
    return subject,'\n\n'.join(blocks+[footer])

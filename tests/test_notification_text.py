"""Messages must identify the operation without disclosing arbitrary event data."""
import json
import pytest
from test_dispatch import store
from mcj import dispatch, notification_text

def event(event_type,category='mods',**data):
    return {'id':1428,'at':1793118373,'category':category,'event':event_type,'data':json.dumps(data)}


@pytest.mark.parametrize('kind', ['world_import_staged','world_exported','world_deleted','world_applied'])
def test_world_messages_identify_the_actual_world_without_reflecting_private_payload(kind):
    data={'runtime':{'world':'Garden_1211'}} if kind=='world_applied' else {'name':'Garden_1211'}
    for language in ('de','en'):
        for channel in ('email','discord'):
            subject,body=dispatch.render([event(kind,'server',**data,backup_id='PRIVATE-ID',secret='PRIVATE-SECRET')],
                                         language,'https://manager.invalid',channel=channel)
            assert 'Garden_1211' in subject and 'Garden_1211' in body
            assert 'PRIVATE-' not in subject+body
            assert 'Meldungstyp:' not in body and 'message type:' not in body
            if kind=='world_import_staged':
                assert ('erst nach' if language=='de' else 'only after') in body
            elif kind=='world_applied':
                assert ('aktive Spielwelt' if language=='de' else 'active game world') in body


@pytest.mark.parametrize('name', ['@everyone\nPRIVATE-URL',{'secret':'PRIVATE-DATA'},None,7])
def test_invalid_world_identity_is_not_sent_to_mail_or_discord(name):
    for kind in ('world_import_staged','world_exported','world_deleted','world_applied'):
        data={'runtime':{'world':name}} if kind=='world_applied' else {'name':name}
        for language in ('de','en'):
            subject,body=dispatch.render([event(kind,'server',**data)],language,'https://manager.invalid',channel='discord')
            assert not any(value in subject+body for value in ('@everyone','PRIVATE-','None','Meldungstyp:','message type:'))


@pytest.mark.parametrize('kind,de,en', [
    ('settings_applied','Server-Einstellungen','Server settings'),
    ('combined_applied','Server- und Modänderungen','Server and mod changes'),
])
def test_native_apply_results_explain_the_completed_operation(kind,de,en):
    for language,expected in [('de',de),('en',en)]:
        subject,body=dispatch.render([event(kind,'maintenance')],language,'https://manager.invalid')
        assert expected in subject
        assert 'Meldungstyp:' not in body and 'message type:' not in body
        assert ('übernommen' if language=='de' else 'applied') in body


@pytest.mark.parametrize('reason,de,en',[
    ('jar_invalid','keine gültige, vollständige Mod-JAR','not a valid, complete mod JAR'),
    ('jar_unsafe_path','unzulässige Dateipfade','unsafe file paths'),
    ('symlink','Dateiverknüpfung','file link'),
])
def test_rejected_folder_mod_identifies_file_reason_impact_and_remedy(reason,de,en):
    for language,explanation in [('de',de),('en',en)]:
        for channel in ('email','discord'):
            subject,body=dispatch.render([event('manual_file_rejected',filename='example.jar',reason=reason)],
                                         language,'https://manager.invalid',channel=channel)
            assert 'example.jar' in subject and 'example.jar' in body
            assert explanation in body
            assert ('aktive Welt wurden dabei nicht verändert' if language=='de' else 'active world were not changed') in body
            assert ('Originaldatei' if language=='de' else 'original file') in body
            assert 'Lies die Prüfung unter Mods' not in body and 'Read its check result under Mods' not in body


@pytest.mark.parametrize('reason',['PRIVATE-RAW-ERROR',{'private':'PRIVATE-RAW-ERROR'},None,42])
def test_unknown_folder_rejection_reason_is_not_exposed_or_treated_as_a_lookup_key(reason):
    for language in ('de','en'):
        for channel in ('email','discord'):
            subject,body=dispatch.render([event('manual_file_rejected',filename='example.jar',reason=reason)],
                                         language,'https://manager.invalid',channel=channel)
            assert 'PRIVATE-RAW-ERROR' not in subject+body
            assert ('nicht installiert' if language=='de' else 'not installed') in body

@pytest.mark.parametrize('language,joined,left',[
    ('de','RomanG ist dem Server beigetreten.','RomanG hat den Server verlassen.'),
    ('en','RomanG joined the server.','RomanG left the server.'),
])
def test_player_identity_is_in_email_and_discord(language,joined,left):
    for channel in ('email','discord'):
        subject,body=dispatch.render([event('player_login','player',name='RomanG')],language,'https://manager.invalid',channel=channel)
        assert joined in body and 'RomanG' in subject
        assert left in dispatch.render([event('player_logout','player',name='RomanG')],language,'https://manager.invalid',channel=channel)[1]
        assert '#1428' not in body

def test_old_role_event_resolves_player_and_new_group(store):
    identifier='00000000-0000-0000-0000-000000000001'
    with store.db() as db:db.execute('INSERT INTO players(uuid,name,first_seen) VALUES(?,?,?)',(identifier,'RomanG',1))
    for language,expected in [('de','RomanG hat jetzt die Spielergruppe „Administrator“.'),('en','RomanG now belongs to the Administrator player group.')]:
        _,body=dispatch.render([event('player_role','player',uuid=identifier,role='administrator',reason='PRIVATE-BAN-REASON')],language,'https://manager.invalid',store)
        assert expected in body and 'PRIVATE-BAN-REASON' not in body

def test_observed_client_pack_deletion_is_explained_with_impact():
    for language,meaning,impact in [('de','2 Clientpakete wurden gelöscht','Mods auf dem laufenden Server bleiben installiert'),('en','2 client packs were deleted','Mods on the running server remain installed')]:
        subject,body=dispatch.render([event('client_pack_deleted',ids=['PRIVATE-ID-1','PRIVATE-ID-2'],revoked_links=3)],language,'https://manager.invalid')
        assert meaning in body and impact in body and '3' in body
        assert 'PRIVATE-ID' not in body and 'Neues Ereignis' not in body and 'New event' not in body

def test_version_search_does_not_claim_a_server_upgrade():
    _,body=dispatch.render([event('stable_versions_checked','server',latest_stable='26.3',count=103)],'de','https://manager.invalid')
    assert '26.3' in body and 'nicht gewechselt' in body
    assert 'Neues Ereignis' not in body

def test_queued_and_failed_jobs_identify_the_work_without_false_rollback():
    for language,operation in [('de','Mod-Updates prüfen'),('en','Check mod updates')]:
        _,queued=dispatch.render([event('job_queued','maintenance',kind='mod_check')],language,'https://manager.invalid')
        _,failed=dispatch.render([event('job_failed','maintenance',kind='mod_check')],language,'https://manager.invalid')
        assert operation in queued and operation in failed
        assert 'wiederhergestellt' not in failed and 'restored the previous' not in failed

@pytest.mark.parametrize('kind,de,en',[
    ('job_queued','Vorgemerkt: Backup erstellen','Queued: Create a backup'),
    ('job_failed','Fehlgeschlagen: Backup erstellen','Failed: Create a backup'),
    ('job_approved','Freigegeben: Backup erstellen','Approved: Create a backup'),
    ('job_cancelled','Verworfen: Backup erstellen','Cancelled: Create a backup'),
])
def test_notification_subject_identifies_job_state_before_opening(kind,de,en):
    for language,expected in [('de',de),('en',en)]:
        for channel in ('email','discord'):
            subject,body=dispatch.render([event(kind,'maintenance',kind='backup')],language,'https://manager.invalid',channel=channel)
            assert subject.endswith(expected)
            assert '\n'+expected+'\n' in body

@pytest.mark.parametrize('failed,unresolved',[(0,0),(1,0),(0,1),(1,2)])
def test_english_update_summary_keeps_sentences_separate(failed,unresolved):
    _,body=dispatch.render([event('update_check_completed',checked=3,updates=0,failed=failed,unresolved=unresolved)],'en','https://manager.invalid')
    assert '. See Mods for the results.' in body
    assert '.See ' not in body

def test_one_unresolved_mod_uses_singular_in_both_languages():
    for language,expected in [('de','Bei 1 Mod blieb das Ergebnis offen.'),('en','unresolved for 1 mod.')]:
        _,body=dispatch.render([event('update_check_completed',checked=3,updates=0,unresolved=1)],language,'https://manager.invalid')
        assert expected in body

def test_missing_results_are_not_rephrased_as_no_updates():
    _,body=dispatch.render([event('update_check_completed',checked=3)],'de','https://manager.invalid')
    assert 'keine Updates' not in body and '3 Mods' in body
    _,body=dispatch.render([event('update_check_completed',checked=3,updates=0,failed=1,unresolved=1)],'de','https://manager.invalid')
    assert '1 Mod konnte nicht geprüft' in body and 'Ergebnis offen' in body
    assert 'Alle Mods sind aktuell' not in body

def test_staged_mod_change_does_not_claim_it_is_already_active(store):
    with store.db() as db:
        db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,updated) VALUES(?,?,?,?,?,?,?)',
                   ('m1','create.jar','0'*64,json.dumps({'mods':[{'name':'Create'}]}),'manual','installed',1))
    _,body=dispatch.render([event('mod_desired_changed',id='m1',enabled=True)],'de','https://manager.invalid',store)
    assert 'Create soll aktiviert werden' in body
    assert 'vorgemerkt' in body and 'bestätigten Übernahme' in body

def test_event_payloads_and_mentions_are_not_copied_to_notifications():
    value=event('player_login','player',name='@everyone\nhttps://secret.invalid/TOKEN',password='PRIVATE-PASSWORD',secret='PRIVATE-SECRET')
    for channel in ('email','discord'):
        subject,body=dispatch.render([value],'de','https://manager.invalid',channel=channel)
        assert all(x not in subject+body for x in ['@everyone','secret.invalid','TOKEN','PRIVATE-PASSWORD','PRIVATE-SECRET'])
    _,body=dispatch.render([event('client_pack_deleted',ids=['PRIVATE-ID'],revoked_links=True)],'de','https://manager.invalid')
    assert 'True' not in body

def test_discord_batches_keep_complete_messages_and_a_remainder_notice():
    events=[event('backup_verified','backup') for _ in range(20)]
    subject,body=dispatch.render(events,'de','https://manager.invalid',channel='discord')
    assert len(subject+'\n'+body)<1900
    assert 'weitere Meldungen' in body and body.endswith('https://manager.invalid')
    assert 'in einer getrennten Testumgebung prüfen.' in body
    _,email=dispatch.render(events,'de','https://manager.invalid')
    assert email.count('Dein Backup wurde erstellt')==20
    long_origin='https://manager.invalid/'+('a'*220)
    subject,body=dispatch.render(events,'de',long_origin,channel='discord')
    assert len(subject+'\n'+body)<1900 and body.endswith(long_origin)


@pytest.mark.parametrize('kind',['job_queued','job_approved','job_cancelled','job_failed'])
@pytest.mark.parametrize('operation,de,en',[
    ('start','Minecraft-Server starten','Start Minecraft server'),
    ('stop','Minecraft-Server stoppen','Stop Minecraft server'),
    ('restart','Minecraft-Server neu starten','Restart Minecraft server'),
])
def test_server_job_notifications_name_the_actual_action(store,kind,operation,de,en):
    identifier='a'*32
    with store.db() as db:
        db.execute('INSERT INTO jobs(id,kind,payload,actor,created,updated,state,mode,approved) VALUES(?,?,?,?,?,?,?,?,?)',
                   (identifier,'server',json.dumps({'operation':operation,'private':'PRIVATE-PAYLOAD'}),1,1,1,'queued','manual',1))
    for language,label in [('de',de),('en',en)]:
        for channel in ('email','discord'):
            for data in ({'job':identifier,'kind':'server'},{'id':identifier}):
                subject,body=dispatch.render([event(kind,'maintenance',**data)],language,'https://manager.invalid',store,channel)
                assert label in subject and label in body
                assert 'PRIVATE-PAYLOAD' not in subject+body


@pytest.mark.parametrize('payload',['{broken','[]','null','{"operation":"PRIVATE-UNKNOWN"}'])
def test_unreadable_server_job_payload_keeps_a_safe_description(store,payload):
    identifier='b'*32
    with store.db() as db:
        db.execute('INSERT INTO jobs(id,kind,payload,actor,created,updated,state,mode,approved) VALUES(?,?,?,?,?,?,?,?,?)',
                   (identifier,'server',payload,1,1,1,'queued','manual',1))
    for language,label in [('de','Minecraft-Server steuern'),('en','Control the Minecraft server')]:
        subject,body=dispatch.render([event('job_queued','maintenance',job=identifier,kind='server')],language,'https://manager.invalid',store)
        assert label in subject and label in body
        assert 'PRIVATE-UNKNOWN' not in subject+body and '{broken' not in subject+body

def test_discord_and_mail_delivery_use_the_same_concrete_description(store,monkeypatch):
    with store.db() as db:db.execute('UPDATE users SET notifications=? WHERE id=1',(json.dumps({'enabled':True,'categories':['player']}),))
    cfg=store.get('discord');cfg.update(enabled=True,events=['player'],language='de')
    store.set('discord',cfg,True)
    dispatch.queue_events(store)
    store.event('player','player_login',data={'name':'RomanG'})
    dispatch.queue_events(store)
    received=[]
    monkeypatch.setattr(dispatch.notify,'send_email',lambda *args,**kwargs:(received.append(args[3]) or {'status':'smtp_accepted'}))
    monkeypatch.setattr(dispatch.notify,'send_discord',lambda *args,**kwargs:received.append(args[1]))
    while dispatch.dispatch_one(store,'https://manager.invalid'):pass
    assert len(received)==2 and all('RomanG ist dem Server beigetreten.' in body for body in received)

def test_update_summary_includes_curseforge_results_and_is_not_emitted_early(store,monkeypatch):
    from mcj import sources,mods
    # A provider-specific scan alone must not announce completion of every provider.
    mods.check_modrinth(store)
    with store.db() as db:assert db.execute("SELECT COUNT(*) FROM events WHERE event='update_check_completed'").fetchone()[0]==0
    origin={'provider':'curseforge','project_id':123,'file_id':456,'url':'https://www.curseforge.com/minecraft/mc-mods/create'}
    with store.db() as db:
        db.execute('INSERT INTO mods(id,filename,sha256,metadata,source,state,updated,origin) VALUES(?,?,?,?,?,?,?,?)',
                   ('m1','create.jar','0'*64,'{}','curseforge','installed',1,json.dumps(origin)))
    monkeypatch.setattr(mods,'check_modrinth',lambda st:None)
    class Provider:
        def __init__(self,st):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,path):return {'id':123}
        def file(self,*args):return {'id':457,'displayName':'2.0','releaseType':1}
    monkeypatch.setattr(sources,'CurseForge',Provider)
    sources.check_updates(store)
    with store.db() as db:rows=list(db.execute("SELECT data FROM events WHERE event='update_check_completed'"))
    assert len(rows)==1
    result=json.loads(rows[0]['data'])
    assert result=={'checked':1,'updates':1,'failed':0,'unresolved':0}
    assert 'Ein Update ist verfügbar.' in dispatch.render([event('update_check_completed',**result)],'de','https://manager.invalid')[1]

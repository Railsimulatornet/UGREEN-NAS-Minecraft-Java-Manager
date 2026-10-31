'use strict';
Object.assign(TEXT.de,{
 setupWizard:'Ersteinrichtungsassistent',setupWizardIntro:'Server, Freigaben, Sicherungen und optionale Dienste Schritt für Schritt durchgehen. Jederzeit erneut aufrufbar.',
 setupWelcome:'Willkommen',setupServer:'Server',setupAccess:'Zugänge',setupBackups:'Sicherungen',setupFinish:'Abschluss',setupProgress:'Einrichtungsschritte',
 setupWelcomeIntro:'Dein Administratorzugang mit Passwort und Zweifaktor-Anmeldung ist eingerichtet. Im nächsten Schritt „Server“ kannst du Minecraft-, Java- und Modloader-Version auswählen. Hier siehst du zunächst den aktuell installierten Stand.',
 setupSafetyHint:'Hier wählst du deine Grundeinstellungen. Für Änderungen am laufenden Minecraft-Server wählst du den Zeitpunkt der Übernahme selbst.',
 setupServerIntro:'Prüfe Minecraft-Version, Arbeitsspeicher, Welt und Spielregeln passend zu deinem NAS und deinen Mitspielern.',
 setupServerHint:'Änderungen an Server oder Welt werden gesammelt und vor der Übernahme mit Sicherung und Servertest geprüft. Für einen Neustart wählst du den Zeitpunkt selbst.',
 setupAccessIntro:'Entscheide bewusst, ob nur dein Heimnetz oder auch externe Spieler und Webbenutzer zugreifen dürfen.',
 setupAccessHint:'Für den Webzugang richtest du HTTPS-Adresse und Reverse-Proxy außerhalb des Managers ein. Minecraft verwendet eine eigene Spieladresse mit Spielport. Die Freigaben im Manager ersetzen keine Netz- oder Routerkonfiguration. Nutze für die Einrichtung eine geprüfte Heimnetzverbindung.',
 setupBackupsIntro:'Lege Sicherungsintervall und Aufbewahrung fest. Bevor du wichtige Änderungen vornimmst, erstelle eine Sicherung und teste ihre Wiederherstellung isoliert.',
 setupVerifiedBackups:'Geprüfte Sicherungsarchive',setupBackupHint:'Ein geprüftes Archiv ist nicht automatisch ein erfolgreicher Restore-Test. Unter Backups kannst du beides getrennt nachvollziehen und einen isolierten Restore-Test starten.',
 setupFinishIntro:'Die Grundeinstellungen sind durchgesehen. Zusätzliche Benutzer, Benachrichtigungen und Mods kannst du jetzt oder später einrichten.',
 setupConfigured:'Konfiguriert',setupOptional:'Optional · noch nicht konfiguriert',
 setupOptionalHint:'Wenn du E-Mail-Codes bei der Anmeldung bestätigt hast, ist der Mailversand bereits eingerichtet. Mit einer Authenticator-App ist der Mailversand optional; richte ihn für Passwortwiederherstellung und Benachrichtigungen unter E-Mail-Versand ein und prüfe eine Testmail. Discord und der Modanbieter-Schlüssel sind optional.',
 setupCompletionHint:'Du kannst diese Einstellungen später wieder öffnen. Ein Zugriff aus dem Internet wird erst möglich, wenn du ihn ausdrücklich freigibst und die nötigen Netzwerk-Einstellungen eingerichtet hast.',
 setupReviewed:'Ich habe die Hinweise gelesen und meine Einstellungen geprüft.',setupNext:'Weiter',setupBack:'Zurück',setupLater:'Später fortsetzen',setupComplete:'Einrichtung abschließen',setupCompleted:'Einrichtungsassistent abgeschlossen',setupResume:'Einrichtung fortsetzen',setupReturnHint:'Der Einrichtungsassistent ist pausiert. Du kannst hier zum letzten Schritt zurückkehren.',setup_review_required:'Bitte bestätige die Abschlussprüfung im letzten Schritt.'
});
Object.assign(TEXT.en,{
 setupWizard:'Setup assistant',setupWizardIntro:'Review your server, access, backups and optional services step by step. You can reopen this at any time.',
 setupWelcome:'Welcome',setupServer:'Server',setupAccess:'Access',setupBackups:'Backups',setupFinish:'Finish',setupProgress:'Setup steps',
 setupWelcomeIntro:'Your administrator password and two-factor sign-in are ready. In the next step, Server, you can choose Minecraft, Java and mod-loader versions. This page shows the currently installed versions.',
 setupSafetyHint:'Choose your basic settings here. You decide when changes to the running Minecraft server may be applied.',
 setupServerIntro:'Review the Minecraft version, memory, world and game rules for your NAS and players.',
 setupServerHint:'Server and world changes are collected, backed up and tested before applying. You choose when a required restart may happen.',
 setupAccessIntro:'Decide whether access is limited to your home network or also available to external players and web users.',
 setupAccessHint:'Configure the HTTPS address and reverse proxy for web access outside the manager. Minecraft uses a separate game address and port. Manager permissions do not replace network or router configuration. Use a verified local connection for setup.',
 setupBackupsIntro:'Choose a backup interval and retention. Before important changes, create a backup and test its restoration in isolation.',
 setupVerifiedBackups:'Verified backup archives',setupBackupHint:'A verified archive is not automatically a successful restore test. The Backups page shows both separately and lets you start an isolated restore test.',
 setupFinishIntro:'The basic settings have been reviewed. You can set up additional users, notifications and mods now or later.',
 setupConfigured:'Configured',setupOptional:'Optional · not configured yet',
 setupOptionalHint:'If you confirmed an email code at sign-in, outgoing email is already set up. With an authenticator app, outgoing email is optional; set it up under Email delivery and check a test email to use password recovery and notifications. Discord and the mod-provider key are optional.',
 setupCompletionHint:'You can reopen these settings later. Internet access requires your explicit approval and the corresponding network configuration.',
 setupReviewed:'I have read the guidance and reviewed my settings.',setupNext:'Next',setupBack:'Back',setupLater:'Continue later',setupComplete:'Finish setup',setupCompleted:'Setup assistant completed',setupResume:'Resume setup',setupReturnHint:'Setup is paused. Resume here to return to the last step.',setup_review_required:'Please confirm the review on the final step.'
});
Object.assign(TEXT.de,{
 setupVersionCatalogUnavailable:'Der offizielle Minecraft-Versionskatalog konnte noch nicht geladen werden. Deshalb erscheint zunächst nur die installierte Minecraft-Version. Prüfe die Internetverbindung des NAS und klicke auf „Stabile Versionen suchen“. Java und Modloader kannst du bereits auswählen; die Kombination wird vor der Übernahme geprüft.',
 setupStartEasy:'Für den ersten Start kannst du die installierte Minecraft-Version und die vorhandenen Vorgaben beibehalten. Die Einrichtung lässt sich jederzeit später ändern.',
 setupServerSteps:'So gehst du vor',setupServerMemory:'Öffne „Server-Einstellungen“, wenn du mehr oder weniger RAM zuweisen möchtest. Lass Speicher für das NAS und andere Apps frei; der Manager prüft die Reserve.',
 setupServerFlight:'Flugzeuge aus einer Mod? Suche in den Server-Einstellungen nach „Flugzeug“ und prüfe allow-flight. Die Erklärung beim Schalter hilft dir weiter.',
 setupServerWorld:'Für den ersten Start kannst du die vorhandene Welt behalten. Eine neue Welt legst du unter „Welten“ an; dort wird auch zwischen Welten gewechselt.',
 setupSettingsReturn:'Wenn du eine Einstellungsseite öffnest: Änderungen speichern beziehungsweise vormerken, das Fenster schließen und oben „Einrichtung fortsetzen“ wählen. Noch nicht übernommene Änderungen stehen unter „Gesammelte Änderungen“.',
 setupAccessLocal:'Einfacher Einstieg: Lass den Zugriff von außerhalb zunächst ausgeschaltet. Das Heimnetz ist dein eigenes Netz zu Hause; ein Minecraft-Spielerkonto ist kein Web-Benutzerkonto.',
 setupAccessExplain:'Begriffe für den Zugang von unterwegs',setupAccessDns:'Webadresse / DNS: der Name, den du im Browser eingibst. Er muss auf deinen Anschluss beziehungsweise deinen eingerichteten Zugang zeigen.',
 setupAccessProxy:'Reverse-Proxy und HTTPS: dein vorgeschalteter Webdienst, der verschlüsselte Browseranfragen an den Manager weitergibt. Ein gültiges Zertifikat gehört dazu.',
 setupAccessRouter:'Router-Portweiterleitung: eine separate Freigabe im Router für Verbindungen von außerhalb. Der Schalter im Manager legt sie nicht an. Die interne Fernsteuerung RCON nicht nach außen freigeben.',
 setupBackupEasy:'Guter Start: automatische Sicherungen eingeschaltet lassen und ein Intervall sowie eine Aufbewahrungsdauer wählen, die zu deinen Spielzeiten und deinem Speicherplatz passen.',
 setupBackupSteps:'Unter „Backups“ mit „Backup jetzt“ eine Sicherung erstellen. Danach beim fertigen Eintrag „Wiederherstellung testen“ wählen. Dabei wird die Sicherung in einer getrennten Testumgebung wiederhergestellt; eure aktive Spielwelt wird dafür nicht ersetzt.',
 setupFinishEasy:'Für den Anfang brauchst du keine Discord-Anbindung und keinen Modanbieter-Schlüssel. Weitere Webkonten nur für Personen anlegen, die den Manager bedienen sollen. Mitspieler brauchen dafür kein Webkonto.'
});
Object.assign(TEXT.en,{
 setupVersionCatalogUnavailable:'The official Minecraft version catalogue has not loaded yet, so only the installed Minecraft version is shown for now. Check the NAS internet connection and click Find stable versions. Java and mod loader can already be selected; the combination is checked before applying.',
 setupStartEasy:'For your first start, keep the installed Minecraft version and existing defaults. You can change the setup later.',
 setupServerSteps:'What to do',setupServerMemory:'Open “Server settings” to adjust RAM. Leave memory for your NAS and other apps; the manager checks the reserve.',
 setupServerFlight:'Using modded aircraft? Search server settings for “aircraft” and review allow-flight. Read the explanation beside the switch.',
 setupServerWorld:'Keep the existing world for your first start. Use “Worlds” to create another world or switch between worlds.',
 setupSettingsReturn:'When opening a settings page: save or collect your changes, close its window and choose “Resume setup” at the top. Changes not yet applied appear under “Collected changes”.',
 setupAccessLocal:'Easy starting point: leave external access disabled initially. Your home network is your own network at home; a Minecraft player account is separate from a web account.',
 setupAccessExplain:'Terms for access away from home',setupAccessDns:'Web address / DNS: the name entered in your browser. It must point to your connection or configured access service.',
 setupAccessProxy:'Reverse proxy and HTTPS: your front-end web service forwarding encrypted browser requests to the manager. This requires a valid certificate.',
 setupAccessRouter:'Router port forwarding: a separate router setting for incoming connections. The manager switch does not create it. Do not expose the internal RCON remote control publicly.',
 setupBackupEasy:'Good starting point: keep automatic backups enabled and choose an interval and retention period that suit your play sessions and available storage.',
 setupBackupSteps:'On “Backups”, choose “Back up now”. On the completed entry, choose “Test restoration”. This restores the backup in a separate test environment without replacing your active world.',
 setupFinishEasy:'Discord and a mod-provider key are optional. Create additional web accounts only for people who should operate the manager. Players do not need a web account.'
});
let setupWizardStep=0;

function setupReturnBanner(){
 const banner=$('setup-assistant');
 if(!banner)return;
 banner.hidden=false;
 banner.replaceChildren(node('span',{text:t('setupReturnHint')}),button('setupBackToWizard',()=>setupWizard(setupWizardStep)));
}

async function setupWizardSettings(category){
 const returnStep=setupWizardStep;
 // Keep the return action beside the opened page, including long forms.
 const navigation=()=>node('nav',{class:'setup-subview-navigation','aria-label':t('setupBackToWizard')},button('setupBackToWizard',()=>setupWizard(returnStep)),paragraph('setupSubviewHint','hint'));
 await settings(category,'',{onShow:()=>{$('modal-content').prepend(navigation());$('modal-content').append(navigation());}});
 setupReturnBanner();
}

async function setupMoveStep(step){
 const move=async()=>{await api('/setup',{step});await setupWizard(step);};
 if(settingsDraftDirty()){requestUnsavedDecision(()=>attempt(move));return;}
 await move();
}

function setupWizardPage(page){
 const open=async()=>{closeModal(true);state.page=page;await renderPage();setupReturnBanner();};
 if(settingsDraftDirty()){requestUnsavedDecision(()=>attempt(open));return;}
 return open();
}

async function setupWizard(chosen=null){
 const data=await api('/setup');
 const step=chosen===null?(data.completed?0:data.step):chosen;
 setupWizardStep=step;
 const titles=['setupWelcome','setupServer','setupAccess','setupBackups','setupFinish'];
 const body=node('div',{class:'setup-wizard stack'});
 const progress=node('ol',{class:'setup-steps','aria-label':t('setupProgress')},titles.map((title,index)=>node('li',{...(index===step?{'aria-current':'step'}:{}),class:index===step?'current':''},node('span',{text:String(index+1)}),t(title))));
 body.append(progress,node('h3',{text:t(titles[step])}));
 const summary=rows=>node('dl',{class:'setup-facts'},rows.map(([label,value])=>[node('dt',{text:t(label)}),node('dd',{text:value})]));
 if(step===0){
  body.append(paragraph('setupWelcomeIntro'),paragraph('setupStartEasy','info-box'),paragraph('setupSafetyHint','hint'),summary([
   ['minecraftVersion',data.server.version+' · '+loaderLabel(data.server)],
   ['javaVersion','Java '+data.server.java],['infraWebAddress',data.web_address]
  ]));
 }
 if(step===1){
  body.append(paragraph('setupServerIntro'),summary([
   ['minecraftVersion',data.server.version+' · '+loaderLabel(data.server)],
   ['memory',data.server.memory_mb?bytes(data.server.memory_mb*1024**2):'—']
  ]),node('ol',{class:'setup-guide'},['setupServerMemory','setupServerWorld','setupServerFlight'].map(key=>node('li',{text:t(key)}))),paragraph('setupServerHint','hint'),paragraph('setupSettingsReturn','hint'),node('div',{class:'form-actions'},button('serverProperties',()=>setupWizardSettings('serverProperties')),button('worldManagement',()=>setupWizardSettings('worldManagement')),button('gameRules',()=>setupWizardSettings('gameRules'))));
 }
 if(step===1){
  const runtime=await runtimeSettings(null,true);decorateSettingsPanel(runtime,'runtimeSettings','server');
  body.insertBefore(node('details',{class:'setup-runtime-editor',open:true},node('summary',{text:t('setupVersionEditor')}),runtime),body.children[3]);
 }
 if(step===2){
  body.append(await playerAdmissionPanel());
  body.append(paragraph('setupAccessIntro'),paragraph('setupAccessLocal','info-box'),node('p',{text:data.web_address}),paragraph('setupAccessHint','hint'),node('details',{},node('summary',{text:t('setupAccessExplain')}),node('ul',{class:'setup-guide'},['setupAccessDns','setupAccessProxy','setupAccessRouter'].map(key=>node('li',{text:t(key)})))),paragraph('setupSettingsReturn','hint'),button('infrastructure',()=>setupWizardSettings('infrastructure')));
 }
 if(step===3){
  const maintenance=(await api('/settings')).maintenance;
  const enabled=input('checkbox');enabled.checked=!!maintenance.backup_enabled;
  const interval=input('number',maintenance.backup_minutes,{min:5,max:1440,required:true});
  const retention=input('number',maintenance.retention_days,{min:1,max:90,required:true});
  const saved=node('p',{class:'validation-status',role:'status'});
  const editor=form([node('label',{class:'checkbox-field'},enabled,t('backupEnabled')),node('div',{class:'setting-grid'},field('backupMinutes',interval),field('retentionDays',retention)),paragraph('setupBackupSaveHint','hint')],'save',async()=>{
   await api('/settings',{section:'maintenance',value:{automatic:!!maintenance.automatic,check_minutes:maintenance.check_minutes,backup_enabled:enabled.checked,backup_minutes:Number(interval.value),retention_days:Number(retention.value)}});
   markSettingsFormSaved(editor);saved.textContent=t('setupBackupSaved');toast(t('saved'));
  });
  body.append(paragraph('setupBackupsIntro'),paragraph('setupBackupEasy','info-box'),editor,saved,summary([['setupVerifiedBackups',String(data.backups.verified_count)]]),paragraph('setupBackupSteps'),paragraph('setupBackupHint','hint'),node('div',{class:'form-actions'},button('schedules',()=>setupWizardSettings('schedules')),button('backups',()=>setupWizardPage('backups'))));
 }

 let reviewed;
 if(step===4){
  reviewed=input('checkbox');reviewed.required=true;
  body.append(paragraph('setupFinishIntro'),paragraph('setupFinishEasy'),summary([['smtp',t(data.mail_configured?'setupConfigured':'setupOptional')],['setupVerifiedBackups',String(data.backups.verified_count)]]),paragraph('setupOptionalHint','hint'),node('div',{class:'form-actions'},button('smtp',()=>setupWizardSettings('smtp')),button('users',()=>setupWizardSettings('users')),button('mods',()=>setupWizardPage('mods'))),paragraph('setupCompletionHint','info-box'),node('label',{class:'checkbox-field'},reviewed,t('setupReviewed')));
 }
 const actions=node('div',{class:'form-actions setup-actions'});
 if(step>0)actions.append(button('setupBack',()=>setupMoveStep(step-1)));
 actions.append(button('setupLater',()=>{closeModal();setupReturnBanner();}));
 if(step<4)actions.append(button('setupNext',()=>setupMoveStep(step+1),'primary'));
 else actions.append(button('setupComplete',async()=>{if(!reviewed.checked){reviewed.reportValidity();return;}await api('/setup',{step:4,complete:true,reviewed:true});$('setup-assistant').hidden=true;closeModal(true);toast(t('setupCompleted'));},'primary'));
 body.append(actions);
 modal('setupWizard',body,{trackDraft:true});
}

Object.assign(TEXT.de,{
 setupBackToWizard:'Zurück zur Einrichtung',setupSubviewHint:'Speichere oder merke deine Änderungen zuerst vor. Danach geht es direkt zum bisherigen Einrichtungsschritt zurück.',setupVersionEditor:'Minecraft, Java und Modloader auswählen',setupBackupSaveHint:'Die Sicherungseinstellungen gelten nach dem Speichern. Die übrigen Wartungseinstellungen bleiben erhalten.',setupBackupSaved:'Sicherungseinstellungen gespeichert.',setupOpenBackups:'Backup-Übersicht öffnen',
 totpScanHelp:'Öffne deine Authenticator-App und scanne diesen QR-Code. Trage anschließend den sechsstelligen Code aus der App unten ein.',totpQrAlt:'QR-Code für die Einrichtung der Authenticator-App',totpManual:'Alternativ: Schlüssel manuell eingeben',totpCopyKey:'Schlüssel kopieren',copied:'Kopiert.'
});
Object.assign(TEXT.en,{
 setupBackToWizard:'Back to setup',setupSubviewHint:'Save or collect your changes first. Then return directly to the same setup step.',setupVersionEditor:'Choose Minecraft, Java and mod loader',setupBackupSaveHint:'Backup settings take effect when saved. Other maintenance settings are kept.',setupBackupSaved:'Backup settings saved.',setupOpenBackups:'Open backup overview',
 totpScanHelp:'Open your authenticator app and scan this QR code. Then enter the six-digit code from the app below.',totpQrAlt:'QR code for setting up your authenticator app',totpManual:'Alternative: enter the key manually',totpCopyKey:'Copy key',copied:'Copied.'
});

Object.assign(TEXT.de,{
 "playerAdmission": "Wer darf dem Spiel beitreten?",
 "playerAdmissionHint": "Mit Namensliste können nur eingetragene Minecraft-Konten beitreten. Wenn du neue Spieler erlaubst, können auch bisher unbekannte, gültige Minecraft-Konten beitreten. Sie starten als Besucher und dürfen erst nach deiner Freigabe mitspielen. Ein Webkonto ist dafür nicht nötig.",
 "playerAdmissionOpen": "Aktuell: Neue Spieler dürfen als Besucher beitreten.",
 "playerAdmissionNamesOnly": "Aktuell: Nur Spieler auf der Namensliste dürfen beitreten.",
 "playerAdmissionPending": "Die gespeicherte Vorgabe und der laufende Server unterscheiden sich. Prüfe die offenen Wartungsaufträge.",
 "playerAdmissionAllow": "Neue Spieler als Besucher erlauben",
 "playerAdmissionClose": "Beitritt auf Namensliste beschränken",
 "playerAdmissionConfirm": "Die Namensliste wird ausgeschaltet. Unbekannte, gültige Minecraft-Konten dürfen danach als Besucher beitreten. Die Schutzkomponente beschränkt ihre Aktionen bis zur Freigabe durch einen Administrator. Vor der Übernahme werden Sicherung und Servertest ausgeführt.",
 "playerAdmissionCloseHint": "Die Namensliste wird eingeschaltet. Künftige Beitritte sind dann auf dort eingetragene Minecraft-Konten beschränkt. Bereits gespeicherte Spielerrollen bleiben erhalten.",
 "playerAdmissionInternet": "Dieser Schalter gilt auch im Heimnetz. Eine Freigabe aus dem Internet ist eine getrennte Entscheidung unter „Infrastruktur“ und benötigt zusätzlich passende Router-Einstellungen.",
 "visitor_admission_requires_verified_guard": "Neue Spieler können noch nicht freigegeben werden: Für die derzeit aktive Schutzkomponente fehlt ein erfolgreicher Besuchertest mit einem echten Minecraft-Client oder der laufende Schutz ist nicht bestätigt. Die Namensliste bleibt als Zugangssperre erhalten. Prüfe den Schutzstatus und installiere eine dafür geprüfte Version.",
 "player_admission_unavailable": "Die Zugangseinstellungen des laufenden Spielservers sind gerade nicht verfügbar. Es wurde nichts geändert. Prüfe den Serverstatus und versuche es erneut.",
 "backupLatestUnavailable": "Die zuletzt erfolgreich erstellte Sicherung ist hier nicht mehr verfügbar. Ihr früherer Erfolg belegt keinen aktuell herunterladbaren Sicherungsstand. Prüfe die Backup-Liste und erstelle eine neue Sicherung.",
 "setupBackupSteps": "Unter „Backups“ mit „Backup jetzt“ eine Sicherung erstellen. Danach beim fertigen Eintrag „Wiederherstellung testen“ wählen. Dabei wird die Sicherung getrennt geprüft; eure aktive Spielwelt bleibt unverändert.",
 "setupBackupHint": "„Archiv geprüft“ bedeutet, dass die Sicherungsdatei vollständig und lesbar ist. Ob daraus ein Minecraft-Server startet, zeigt erst „Wiederherstellung testen“. Beide Ergebnisse stehen unter Backups.",
 "setupVersionCatalogUnavailable": "Die offizielle Versionsliste konnte noch nicht geladen werden. Prüfe die Internetverbindung des NAS und versuche „Stabile Versionen suchen“ erneut. Auswählbar bleiben nur die mit der Schutzkomponente geprüften Kombinationen."
});
Object.assign(TEXT.en,{
 "playerAdmission": "Who may join the game?",
 "playerAdmissionHint": "With the name list enabled, only listed Minecraft accounts may join. If you allow new players, previously unknown, valid Minecraft accounts may also join. They start as visitors and need your approval before playing. They do not need a web account.",
 "playerAdmissionOpen": "Currently: New players may join as visitors.",
 "playerAdmissionNamesOnly": "Currently: Only players on the name list may join.",
 "playerAdmissionPending": "The saved setting differs from the running server. Check pending maintenance jobs.",
 "playerAdmissionAllow": "Allow new players as visitors",
 "playerAdmissionClose": "Restrict joining to the name list",
 "playerAdmissionConfirm": "The name list will be disabled. Previously unknown, valid Minecraft accounts may then join as visitors. The protection component limits their actions until an administrator approves them. A backup and server test run before the change is applied.",
 "playerAdmissionCloseHint": "The name list will be enabled. Future joins will be restricted to Minecraft accounts listed there. Saved player roles are retained.",
 "playerAdmissionInternet": "This setting also applies within your home network. Internet access is a separate decision under Infrastructure and also requires suitable router settings.",
 "visitor_admission_requires_verified_guard": "New players cannot be enabled yet: the active protection component lacks a successful visitor test with a real Minecraft client, or its current protection status is unconfirmed. The name list remains an access barrier. Check the protection status and install a version verified for this purpose.",
 "player_admission_unavailable": "The running game server’s access settings are unavailable. Nothing was changed. Check server status and try again.",
 "backupLatestUnavailable": "The most recently created successful backup is no longer available here. Its earlier success does not confirm an archive you can download now. Check the backup list and create a new backup.",
 "setupBackupSteps": "On Backups, choose Back up now. On the completed entry, choose Test restoration. The backup is checked separately; your active world remains unchanged.",
 "setupBackupHint": "Archive verified means the backup file is complete and readable. Test restoration separately checks whether a Minecraft server starts from it. Both results are shown on Backups.",
 "setupVersionCatalogUnavailable": "The official version list could not be loaded. Check the NAS internet connection and try Find stable versions again. Only combinations tested with the protection component can be selected."
});

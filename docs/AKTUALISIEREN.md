# Manager über UGOS aktualisieren

Hier erfährst du, wie du eine vorhandene MCJ-Installation aktualisierst. Dabei werden nur Manager und Steuerungsdienst ersetzt. Minecraft-Versionen und Mods aktualisierst du getrennt im Manager.

Verwende für das Update dein bestehendes UGOS-Einrichtungsprojekt und behalte dessen Speicherordner bei. Importiere den Minecraft-Datenordner dafür **nicht** als neues Projekt. UGOS kann beim Übernehmen eines Projekt-Speicherpfads die Dateirechte dieses Ordners ändern.

**Voraussetzung:** Manager, Steuerungsdienst und Minecraft müssen vor dem Update laufen und als **gesund** angezeigt werden. Auch ein absichtlich gestoppter Minecraft-Server verhindert derzeit die Aktualisierung. Starte ihn deshalb zuerst. Falls ein Dienst nicht startet oder nicht gesund wird, prüfe seine Containerprotokolle in UGOS. Eine Neuinstallation über den bestehenden Daten behebt diesen Fehler nicht und darf dafür nicht gestartet werden.

1. Warte, bis laufende Wartungsaufträge abgeschlossen sind. Die Aktualisierung bricht bei laufender Wartung ab; du kannst sie danach erneut starten.
2. Lade in **UGOS → Docker → Image** das offizielle Image `railsimulatornet/ugreen-nas-minecraft-java-manager:stable` herunter. Der Kanal enthält ausschließlich erfolgreich geprüfte Veröffentlichungen. Wenn dir eine Image-Datei bereitgestellt wurde, importiere stattdessen diese in UGOS.
3. Öffne unter **Docker → Projekt** das bisherige Einrichtungsprojekt, gewöhnlich `mcj_einrichtung`. Behalte dessen bisherigen Speicherpfad bei.
4. Importiere einmalig [deploy/ugos-aktualisierung.yaml](../deploy/ugos-aktualisierung.yaml) als neue Compose-Konfiguration und wähle **Neu bereitstellen**. Zeigt UGOS danach **Nicht in Betrieb**, klicke auf **Starten**: Das erneute Bereitstellen allein kann das zuvor beendete Einrichtungsprojekt ausgeschaltet lassen. Die Vorlage steht auch unter **Einstellungen → Manager aktualisieren** zum Download bereit.
5. Verfolge das Ergebnis im UGOS-Projektprotokoll. Während der Übernahme ist der Manager kurz nicht erreichbar. Der Minecraft-Spielserver läuft weiter. Lade die Manager-Webseite nach Abschluss neu.

Bei späteren Aktualisierungen genügt es, das neue `stable`-Image herunterzuladen und dieses Aktualisierungsprojekt erneut bereitzustellen. Ist das installierte Image bereits aktuell, meldet der Updater das, ohne die Dienste neu zu starten.

Der Updater öffnet keine eigene Weboberfläche und bindet über UGOS keine Minecraft-Datenordner ein. Er erkennt deine Installation anhand der Kennzeichnungen der vorhandenen Container (Labels). Vor einer Änderung müssen die Compose-Prüfsummen zum tatsächlich laufenden Stand passen. Nur Manager und Steuerungsdienst werden neu erstellt; Welt, Moddateien und Minecraft-Laufzeit werden nicht ersetzt.

Vor der Übernahme erstellt der Helfer eine konsistente, geprüfte Sicherung der Manager-Datenbank sowie der Compose-Konfiguration und Laufzeit-Auswahl. Schlüsseldateien werden ausschließlich auf unveränderten Inhalt, Eigentümer und private Dateirechte geprüft. Der private Rückfallstand liegt unter `mcj_controller/.rollback/ugos-app-…` und enthält vertrauliche Daten; er gehört nicht in öffentliche Supportmeldungen.

Startet die neue Version nicht korrekt oder stimmen die gespeicherten Konten beziehungsweise verschlüsselten Einstellungen nicht mehr mit dem gesicherten Stand überein, stellt der Updater den bisherigen Manager und seine Datenbank wieder her. Der Rückfall wird ausdrücklich als solcher angezeigt. Eine fehlgeschlagene Aktualisierung gilt nicht als erfolgreiche Übernahme.

**Wichtig:** Den Minecraft-Datenordner niemals als Speicherpfad eines neuen UGOS-Projekts wählen. Die Erstinstallation darf nicht über eine bestehende Installation gestartet werden. Verwende auch keine allgemeine rekursive Rechteänderung als Update-Schritt.

Neue Erstinstallation: [README.md](../README.md#deutsch). Erweiterte Wiederherstellung und vorhandene Compose-Identität: [INSTALL-RECOVERY.md](INSTALL-RECOVERY.md).

## English

Use this guide to update an existing MCJ installation. The update replaces only the manager and controller. Update Minecraft versions and mods separately in the manager.

Use the existing UGOS setup project to update. Keep its storage directory. Importing the Minecraft data directory as a new UGOS project can change private file permissions.

**Required before updating:** The manager, controller and Minecraft must all be running and shown as **healthy**. Even an intentionally stopped Minecraft server currently prevents the update. Start it first. If a service fails to start or become healthy, check its container logs in UGOS. Running first-time setup over existing data does not resolve this error and must not be used for this purpose.

1. Wait until running maintenance jobs have finished.
2. In **UGOS → Docker → Image**, download `railsimulatornet/ugreen-nas-minecraft-java-manager:stable`. If you were supplied an image file, import it into UGOS instead.
3. Under **Docker → Project**, open the existing setup project, normally `mcj_einrichtung`. Keep its original storage path.
4. Import [ugos-aktualisierung.yaml](../deploy/ugos-aktualisierung.yaml) once as the replacement Compose configuration and choose **Redeploy**. If UGOS then shows **Not running**, click **Start**: redeploying alone may leave a previously stopped setup project switched off. The template is also available under **Settings → Update manager**.
5. Read the result in the UGOS project log. The manager is briefly unavailable; Minecraft keeps running. Reload the manager after completion.

For later updates, download the latest `stable` image and redeploy the same update project. If the installed image is already current, the updater tells you without restarting the services.

The updater creates and verifies a consistent manager database backup before replacing manager and controller. If the new app fails its health or preserved-data checks, it restores the previous app and database. Check the explicit success or rollback result. Private rollback data under `mcj_controller/.rollback` contains confidential settings and must not be posted in support issues.

Do not run first-time setup over an existing installation or use recursive permission changes as an update step. For new installations, see [README](../README.md#english).

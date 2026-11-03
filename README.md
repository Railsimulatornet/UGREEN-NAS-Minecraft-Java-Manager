# MCJ Manager

[Deutsch](#deutsch) · [English](#english)

**Version 1.0.0**

![Serverübersicht mit Beispieldaten / Server overview with sample data](docs/images/uebersicht.png)

## Deutsch

Mit dem MCJ Manager verwaltest du deinen Minecraft-Java-Server auf einem UGREEN NAS direkt im Browser. Du kannst Spieler freigeben, Mods installieren, Welten wechseln und Backups anlegen oder wiederherstellen. Die Oberfläche gibt es auf Deutsch und Englisch – für den PC und das Smartphone.

**Loslegen:** [Installationspaket herunterladen](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/releases/download/v1.0.0/MCJ-Manager-1.0.0.zip) · [Handbuch](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/releases/download/v1.0.0/Installation-DE.pdf) · [Anleitung online lesen](docs/INSTALLATION-DE.md)

**Schon installiert?** Dann verwende die [Update-Anleitung](docs/AKTUALISIEREN.md). Starte keine Erstinstallation über deinen vorhandenen Daten.

### Was brauche ich?

- Ein UGREEN NAS mit Intel- oder AMD-Prozessor, UGOS und installierter Docker-App. Das Image ist für `linux/amd64` gebaut; ARM-Geräte werden nicht unterstützt.
- Die feste IP-Adresse deines NAS im Heimnetz, zum Beispiel `192.168.1.50`, und eine Internetverbindung des NAS für die Downloads.
- Einen vorhandenen Docker-Ordner, zum Beispiel `/volume1/docker`, sowie freien Arbeitsspeicher und Platz für Welten und Backups.
- Einen aktuellen Browser und eine erreichbare E-Mail-Adresse. Für die Anmeldung wählst du einen Sicherheitscode per E-Mail oder eine Authenticator-App. Für E-Mail-Codes brauchst du zusätzlich die Versanddaten deines E-Mail-Anbieters.
- Zum Mitspielen einen Computer mit Minecraft Java Edition. Jeder Spieler braucht ein eigenes Konto mit gültiger Minecraft-Java-Lizenz; eine Spiellizenz ist nicht enthalten.

Für die normale Installation brauchst du weder SSH noch ein Terminal. Der Manager verwaltet **einen Minecraft-Server pro NAS**.

### So installierst du den Manager

1. Lade die [Einrichtungsvorlage `ugos-einrichtung.yaml`](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/releases/download/v1.0.0/ugos-einrichtung.yaml) herunter. Sie ist auch im Installationspaket enthalten. Verwende nicht die `compose.yaml` aus dem Quellcode.
2. Öffne **UGOS → Docker → Projekt → Erstellen**. Nenne das Projekt `mcj_einrichtung` und wähle dafür einen eigenen, leeren Speicherordner. Importiere die Einrichtungsvorlage.
3. Trage deine NAS-IP bei `NAS_IP` und deinen vorhandenen Docker-Ordner bei `NAS_ORDNER` ein. Zeigt UGOS keine Variablenfelder, ersetze die Platzhalter direkt in der Konfiguration. Die [Anleitung](docs/INSTALLATION-DE.md) zeigt beide Wege.
4. Starte das Projekt. Unter **UGOS → Dateien → dein Docker-Ordner → mcj-einrichtung** findest du anschließend `EINRICHTUNGSCODE.txt` und `Heimnetz-Zertifikat.crt`. Beachte den Bindestrich: Dieser automatisch angelegte Ordner ist nicht der Projektordner `mcj_einrichtung` mit Unterstrich.
5. Prüfe das Zertifikat und richte das Vertrauen nach der [HTTPS-Anleitung](docs/HTTPS.md) ein. Öffne dann `https://DEINE-NAS-IP:8090`. Schalte die Zertifikatsprüfung deines Browsers nicht aus.
6. Gib den Einrichtungscode ein. Lege dein Administratorkonto, neue Speicherordner und das RAM-Budget fest. Lies die Minecraft-EULA und bestätige sie, wenn du zustimmst. Klicke danach auf **Installation starten**.
7. Melde dich nach Abschluss an. Wähle **E-Mail-Sicherheitscode** oder **Authenticator-App (TOTP)** und folge den angezeigten Schritten. Sichere die Wiederherstellungscodes. Der Assistent führt dich anschließend durch Server, Zugänge und Backups.

Das ZIP enthält Vorlagen, Handbücher und die optionale Create-Zugkorrektur, **kein Docker-Image**. UGOS lädt `railsimulatornet/ugreen-nas-minecraft-java-manager:1.0.0` von [Docker Hub](https://hub.docker.com/r/railsimulatornet/ugreen-nas-minecraft-java-manager).

### Welche Versionen funktionieren?

Diese neun Kombinationen sind geprüft. Pro Tabellenzeile wählst du **einen** der drei Modloader:

| Minecraft | Java | Fabric | Forge | NeoForge |
|---|---|---|---|---|
| 1.20.1 | 17 | 0.20.1 | 47.4.28 | 47.1.106 |
| 1.21.1 | 21 | 0.20.1 | 52.1.20 | 21.1.265 |
| 26.3 | 25 | 0.20.1 | 66.1.0 | 26.3.0.99 |

Voreingestellt sind **Minecraft 26.3, NeoForge 26.3.0.99 und Java 25**. Der mitgelieferte Besucherschutz heißt Visitor Guard und hat die eigene Versionsnummer **1.0.7**. Für NeoForge 1.20.1 brauchst du den Loader 47.1.106; er ist nicht mit Forge 47.4.28 austauschbar.

Weitere Einträge im Versionskatalog sind nicht automatisch unterstützt. Zusätzliche Mods müssen zu deiner Kombination passen. Vanilla, Paper, Spigot, Quilt und Bedrock gehören nicht zum unterstützten Umfang. Die [Kompatibilitätsanleitung](docs/KOMPATIBILITAET.md) erklärt die Auswahl und den Versionswechsel.

### Die ersten Spieler und Mods

Webkonto und Minecraft-Konto sind getrennt. Deine Mitspieler brauchen kein Konto für die Weboberfläche. Ein Webadministrator erhält dadurch auch keine Minecraft-Operatorrechte.

Ist die Namensliste aktiv, erlaubst du den ersten Beitritt unter **Übersicht → Serverkonsole** mit `whitelist add DeinSpielername`. Nach dem Beitritt gibst du den Spieler unter **Spieler → Aktionen → Gruppe → Spieler** zum Mitspielen frei. Bis dahin bleibt er Besucher im Zuschauermodus.

Unter **Mods** kannst du Mods suchen, hochladen und auf Updates prüfen. Für die CurseForge-Suche hinterlegst du deinen eigenen API-Schlüssel unter **Einstellungen → Mod-Anbieter**. Änderungen werden erst zum gewählten Zeitpunkt nach Sicherung und Servertest übernommen.

Unter **Client-Modpack** erstellst du das passende `.mrpack` für deine Mitspieler. Sie importieren es in [Prism Launcher](https://prismlauncher.org/wiki/help-pages/zip-import/). Ein freigegebener Download-Link funktioniert ohne Webkonto. Der Name `1.0.0-client.2` bedeutet Manager 1.0.0, Paketnummer 2 – die Minecraft-, Java- und Modloader-Versionen stehen separat dabei. Unklare Mod-Anforderungen kannst du unter **Welche Mods brauchen die Spieler?** zuordnen.

### Backups und Updates

Unter **Backups** kannst du sichern, herunterladen und wiederherstellen. Automatische Sicherungen stellst du unter **Einstellungen → Zeitpläne** ein. Sobald eine Sicherung fällig ist, wartet der Manager, bis seit fünf Minuten niemand mehr spielt. Einen laufenden Server stoppt er für die Sicherung und startet ihn anschließend wieder. Wenn durchgehend gespielt wird, verschiebt sich das Backup. Bewahre wichtige Sicherungen zusätzlich außerhalb des NAS auf.

Manager-Updates laufen getrennt von Minecraft- und Mod-Updates. **Vor einem Manager-Update müssen Manager, Steuerungsdienst und Minecraft laufen und als gesund angezeigt werden.** Starte einen absichtlich gestoppten Spielserver zuerst. Falls ein Dienst nicht startet, prüfe die UGOS-Containerprotokolle – installiere nicht einfach über die vorhandenen Daten neu. Die [Update-Anleitung](docs/AKTUALISIEREN.md) erklärt den Ablauf mit `stable` und die Rückkehr zum vorherigen Stand bei einem Fehler.

### Gut zu wissen

Unter **Einstellungen → Welten** verwaltest du Welten und siehst deren verwendeten Seed. E-Mail- und Discord-Benachrichtigungen richtest du in den Einstellungen ein. Bei E-Mail-Anmeldung ist der Mailversand bereits eingerichtet. Nach einer vollständigen Anmeldung musst du nicht bei jeder normalen Änderung erneut einen Sicherheitscode eingeben.

Wartungsaufträge laufen auf dem NAS weiter, wenn du das Fenster schließt. Ihren Fortschritt findest du unter **Übersicht → Wartung**.

Beginne im Heimnetz. Webzugang und Minecraft-Zugang von außerhalb richtest du getrennt ein: Die Weboberfläche braucht HTTPS, das Spiel eine erreichbare Serveradresse und den Spielport. Router und Reverse-Proxy werden nicht vom Manager eingerichtet. Interne Steuerungs- und RCON-Ports gehören nicht ins Internet.

## English

MCJ Manager lets you manage a Minecraft Java server on your UGREEN NAS in a browser. Approve players, install mods, switch worlds, and create or restore backups. The interface is available in German and English on desktop and mobile.

**Get started:** [Download the installation pack](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/releases/download/v1.0.0/MCJ-Manager-1.0.0.zip) · [Manual](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/releases/download/v1.0.0/Installation-EN.pdf) · [Read the guide online](docs/INSTALLATION-EN.md)

**Already installed?** Follow the [update guide](docs/AKTUALISIEREN.md#english). Do not run first-time setup over existing data.

### What do I need?

- An Intel or AMD UGREEN NAS with UGOS and the Docker app installed. The image is built for `linux/amd64`; ARM devices are not supported.
- A fixed local IP address for your NAS, such as `192.168.1.50`, and an internet connection on the NAS for downloads.
- An existing Docker directory, such as `/volume1/docker`, plus available memory and storage for worlds and backups.
- A modern browser and an email address you can access. Choose email security codes or an authenticator app for sign-in. Email codes also require your email provider's outgoing mail settings.
- A computer with Minecraft Java Edition to play. Each player needs their own account with a valid Minecraft Java licence; a game licence is not included.

Normal installation does not require SSH or a terminal. The manager runs **one Minecraft server per NAS**.

### Install the manager

1. Download the [setup template, `ugos-einrichtung.yaml`](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/releases/download/v1.0.0/ugos-einrichtung.yaml). It is also included in the installation pack. Do not use the `compose.yaml` from the source code.
2. Open **UGOS → Docker → Project → Create**. Name the project `mcj_einrichtung` and choose a separate, empty storage directory. Import the setup template.
3. Set `NAS_IP` to your NAS's IP address and `NAS_ORDNER` to your existing Docker directory. If UGOS has no variables fields, replace the placeholders in the configuration. The [Guide](docs/INSTALLATION-EN.md) covers both options.
4. Start the project. Under **UGOS → Files → your Docker directory → mcj-einrichtung**, you will find `EINRICHTUNGSCODE.txt` and `Heimnetz-Zertifikat.crt`. Note the hyphen: this automatically created directory is separate from the `mcj_einrichtung` project directory with an underscore.
5. Check and trust the certificate as described in the [HTTPS guide](docs/HTTPS.md#english), then open `https://YOUR-NAS-IP:8090`. Do not disable your browser's certificate checks.
6. Enter the setup code. Create your administrator account and choose new storage directories and a memory budget. Read the Minecraft EULA and accept it if you agree, then click **Start installation**.
7. Sign in once setup finishes. Choose **Email security code** or **Authenticator app (TOTP)** and follow the instructions. Save your recovery codes. The wizard then walks you through the server, access and backups.

The ZIP contains templates, manuals and the optional Create train correction, **not a Docker image**. UGOS downloads `railsimulatornet/ugreen-nas-minecraft-java-manager:1.0.0` from [Docker Hub](https://hub.docker.com/r/railsimulatornet/ugreen-nas-minecraft-java-manager).

### Supported versions

These nine combinations have been tested. Choose **one** mod loader from each row:

| Minecraft | Java | Fabric | Forge | NeoForge |
|---|---|---|---|---|
| 1.20.1 | 17 | 0.20.1 | 47.4.28 | 47.1.106 |
| 1.21.1 | 21 | 0.20.1 | 52.1.20 | 21.1.265 |
| 26.3 | 25 | 0.20.1 | 66.1.0 | 26.3.0.99 |

The default is **Minecraft 26.3, NeoForge 26.3.0.99 and Java 25**. The bundled protection mod, Visitor Guard, has its own version number: **1.0.7**. NeoForge for Minecraft 1.20.1 uses loader 47.1.106, which is not interchangeable with Forge 47.4.28.

Other catalogue entries are not automatically supported. Additional mods must match your chosen combination. Vanilla, Paper, Spigot, Quilt and Bedrock are not supported. See the [compatibility guide](docs/KOMPATIBILITAET.md#english) for version selection and switching.

### Your first players and mods

Web accounts and Minecraft accounts are separate. Players do not need a web account, and being a web administrator does not grant Minecraft operator permissions.

With the name list enabled, allow the first account to join using `whitelist add YourPlayerName` under **Overview → Server console**. After it joins, choose **Players → Actions → Group → Player** to let that player play. Until then, the player remains a visitor in spectator mode.

Under **Mods**, you can search for mods, upload files and check for updates. Add your own CurseForge API key under **Settings → Mod providers** to use CurseForge search. Changes are applied at your chosen time after a backup and server test.

Under **Client modpack**, create a matching `.mrpack` for your players to import into [Prism Launcher](https://prismlauncher.org/wiki/help-pages/zip-import/). A shared download link works without a web account. A name such as `1.0.0-client.2` means manager 1.0.0, package number 2; Minecraft, Java and loader versions are listed separately. Use **Which mods do players need?** to resolve unclear mod requirements.

### Backups and updates

Use **Backups** to create, download and restore backups. Set automatic backups under **Settings → Schedules**. When a backup is due, the manager waits until no one has played for five minutes. It stops a running server for the backup and starts it again afterwards. Continuous play delays the backup. Keep additional copies of important backups outside the NAS.

Manager updates are separate from Minecraft and mod updates. **Before updating, the manager, controller and Minecraft must all be running and shown as healthy.** Start an intentionally stopped game server first. If a service will not start, check the UGOS container logs; do not run setup again over existing data. The [update guide](docs/AKTUALISIEREN.md#english) explains the `stable` update channel and rollback if an update fails.

### A few useful details

Manage worlds and view their actual seeds under **Settings → Worlds**. Email and Discord notifications are also configured in Settings. Outgoing email is already configured if you chose email sign-in. Once fully signed in, you do not need to enter another security code for each normal change.

Maintenance jobs continue on the NAS after you close their window. Follow progress under **Overview → Maintenance**.

Start on your home network. Remote web access and Minecraft access are configured separately: the web interface needs HTTPS, while the game needs a reachable server address and game port. The manager does not configure your router or reverse proxy. Never expose internal controller or RCON ports to the internet.

## Hilfe und Sicherheit / Help and security

Fehler meldest du über [GitHub Issues](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/issues). Nenne die Manager-Version, die betroffene Seite und die Schritte bis zum Fehler. Sicherheitsprobleme bitte [vertraulich melden](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/security/advisories/new). **Veröffentliche keine Passwörter, API-Schlüssel, Webhook-Tokens oder Sicherheitscodes.**

Report bugs through [GitHub Issues](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/issues), including the manager version, affected page and steps to reproduce. Report security problems [confidentially](https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/security/advisories/new). **Do not publish passwords, API keys, webhook tokens or security codes.**

Der Steuerungsdienst benötigt weitreichenden Docker-Zugriff auf dem NAS. Gib deshalb nur Personen deines Vertrauens Administratorrechte. Bekannte Einschränkungen und Paketmeldungen stehen in der [Sicherheitsdokumentation](docs/security/IMAGE-SECURITY.md).

The controller needs extensive Docker access on the NAS. Grant administrator access only to people you trust. See the [security documentation](docs/security/IMAGE-SECURITY.md#english) for known limitations and package findings.

## Weitere Informationen / Further reading

[Versionshinweise / Release notes](CHANGELOG.md) · [Zugang wiederherstellen / Recover access](docs/ZUGANG.md) · [Administration und Wiederherstellung / Administration and recovery](docs/INSTALL-RECOVERY.md) · [Entwicklung / Development](docs/ENTWICKLUNG.md)

## Lizenz / Licence

© 2026 Roman Glos. Eigener Projektcode: [MIT](LICENSE). Fremde Komponenten behalten ihre jeweiligen Lizenzen; siehe [NOTICE.txt](NOTICE.txt) und [Lizenzen und Herkunft](docs/LIZENZEN.md).

© 2026 Roman Glos. Original project code: [MIT](LICENSE). Third-party components retain their own licences; see [NOTICE.txt](NOTICE.txt) and [licences and attribution](docs/LIZENZEN.md#english).

Unabhängiges Projekt. Keine offizielle Software von UGREEN, Mojang oder Microsoft. / Independent project. Not official UGREEN, Mojang or Microsoft software.

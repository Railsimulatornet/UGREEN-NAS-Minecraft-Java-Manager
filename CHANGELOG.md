# Versionshinweise / Release notes

## 1.0.1 - Erweiterte Loader-Unterstützung und Korrekturen / Loader support and fixes

### Deutsch

- Fabric, Forge und NeoForge für Minecraft 1.20.1, 1.21.1 und 26.3 mit Java 17, 21 beziehungsweise 25. Die Kompatibilitätsanleitung nennt die genauen geprüften Versionen und Schutzdateien.
- Korrigierter Besucherschutz, passende Clientpakete und geprüfte Rollenwechsel für diese neun Kombinationen.
- Konsolenbefehle ohne Textantwort werden auch unter Forge 1.21.1 korrekt abgeschlossen. Mehrteilige Antworten werden vollständig gelesen; echte Verbindungsfehler bleiben Fehler.
- Wiederherstellung und sauberer Serverstopp wurden korrigiert. Unpassende Mod-Abhängigkeiten werden vor der Übernahme verständlich gemeldet.
- Besondere Dateitypen werden beim Öffnen einer Welt sofort abgewiesen. Eine manipulierte `level.dat` kann die Weltverwaltung dadurch nicht dauerhaft blockieren.
- Anleitungen und beide PDF-Handbücher enthalten dieselben unterstützten Versionen und die Voraussetzungen für Manager-Updates.

### English

- Fabric, Forge and NeoForge for Minecraft 1.20.1, 1.21.1 and 26.3, using Java 17, 21 and 25 respectively. The compatibility guide lists the exact tested versions and protection files.
- Corrected visitor protection, matching client packs and verified role changes for these nine combinations.
- Console commands with no text response now complete correctly on Forge 1.21.1. Multipart replies are read in full; actual connection failures remain errors.
- Corrected restoration and clean server shutdown. Unsatisfied mod dependencies are explained before applying a change.
- Special file types are rejected immediately when opening a world, preventing a tampered `level.dat` from leaving world management stuck indefinitely.
- The guides and both PDF manuals agree on supported versions and the prerequisites for manager updates.

## 1.0.0 - Erste Veröffentlichung / Initial release

### Deutsch

- Geführte Installation auf einem UGREEN NAS und Verwaltung im Browser auf Deutsch und Englisch.
- Geschützte Anmeldung mit Passwort und E-Mail-Code oder Authenticator-App sowie Wiederherstellungscodes.
- Verwaltung von Minecraft, Spielern, Mods, Clientpaketen und Welten für die unterstützten NeoForge-Konfigurationen.
- Sicherungen mit getrenntem Wiederherstellungstest und planbare Wartungsaufträge.
- Optionale Benachrichtigungen per E-Mail und Discord.

### English

- Guided installation on a UGREEN NAS and browser-based management in German and English.
- Protected sign-in with a password and an email code or authenticator app, plus recovery codes.
- Management of Minecraft, players, mods, client packs and worlds for the supported NeoForge configurations.
- Backups with a separate restore test and scheduled maintenance jobs.
- Optional email and Discord notifications.

# Versionshinweise / Release notes

## 1.0.1 - Backup-Verwaltung / Backup management

### Deutsch

- Das Image enthält die APT-Sicherheitskorrektur 3.0.4. Neue SQLite- und zlib-Paketmeldungen sind anhand der verwendeten Aufrufe bewertet und dokumentiert.

- „Löschbare Einträge auswählen“ berücksichtigt dieselben geschützten Rückfallstände wie die Löschprüfung. Ungültig gewordene Auswahlen werden beim Aktualisieren entfernt.
- Alte Verweise auf abgeschlossene Tests, Änderungen und Wiederherstellungen halten Backup-Archive nicht mehr unbegrenzt fest. Die eingestellte Aufbewahrung greift wieder; die zwei neuesten Archive und Sicherungen für ausstehende Aufträge bleiben erhalten.
- Die Anleitungen und Handbücher erklären Aufbewahrung, Löschbestätigung und die verbleibenden Verlaufseinträge.

### English

- The image includes the APT 3.0.4 security fix. Additional SQLite and zlib package findings are documented against the shipped call paths.

- “Select deletable items” uses the same recovery protection as deletion. Selections that are no longer valid are removed when the list refreshes.
- References to past tests, changes and restores no longer keep backup archives indefinitely. The configured retention period applies; the two newest archives and backups needed by pending jobs are retained.
- The guides and manuals explain retention, deletion confirmation and the history records that remain.

## 1.0.0 - Erste Veröffentlichung / Initial release

### Deutsch

- Geführte Installation auf einem UGREEN NAS und Verwaltung im Browser auf Deutsch und Englisch.
- Anmeldung mit Passwort und E-Mail-Code oder Authenticator-App, einschließlich Wiederherstellungscodes.
- Minecraft 1.20.1 mit Java 17, 1.21.1 mit Java 21 und 26.3 mit Java 25, jeweils mit den festgelegten Fabric-, Forge- und NeoForge-Versionen und Visitor Guard 1.0.7.
- Spielerfreigabe, Besucherbeschränkungen, Rollenwechsel und Rechteentzug.
- Mods mit Abhängigkeitsprüfung, passende Clientpakete und Weltenverwaltung.
- Sicherungen, getrennte Wiederherstellungstests, Rücksicherung und Versionswechsel mit Rückfallmöglichkeit.
- Serverkonsole mit vollständigen mehrteiligen Antworten und bestätigtem Abschluss leerer Antworten.
- Sichere Behandlung besonderer Dateitypen in Weltdaten; planbare Wartung sowie optionale Benachrichtigungen per E-Mail und Discord.
- Bebilderte deutsche und englische Handbücher, UGOS-Vorlagen und dokumentierter Updateweg. Die Kompatibilitätsmatrix nennt die genauen geprüften Kombinationen; die Sicherheitsdokumentation erläutert bekannte Paketbefunde.

### English

- Guided installation on a UGREEN NAS and browser-based management in German and English.
- Sign-in with a password and an email code or authenticator app, including recovery codes.
- Minecraft 1.20.1 with Java 17, 1.21.1 with Java 21 and 26.3 with Java 25, each with the pinned Fabric, Forge and NeoForge versions and Visitor Guard 1.0.7.
- Player approval, visitor restrictions, role changes and permission revocation.
- Mods with dependency checks, matching client packs and world management.
- Backups, separate restore tests, restoration and version changes with rollback.
- Server console with complete multipart output and verified completion of empty replies.
- Safe handling of special file types in world data; scheduled maintenance and optional email and Discord notifications.
- Illustrated German and English manuals, UGOS templates and documented updates. The compatibility matrix lists the exact tested combinations; the security documentation explains known package findings.

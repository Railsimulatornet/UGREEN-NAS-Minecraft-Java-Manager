# Kompatibilität / Compatibility — MCJ Manager 1.0.2

## Unterstützte Kombinationen / Supported combinations

Diese neun Kombinationen sind mit den angegebenen Java- und Loader-Versionen geprüft. Jede verwendet Visitor Guard 1.0.7. Andere Katalogeinträge sind keine zugesagte Unterstützung und bleiben ohne passende Abnahme für die Installation gesperrt.

These nine combinations have been tested with the listed Java and loader versions and Visitor Guard 1.0.7. Other catalogue entries do not imply support and remain blocked for installation without the required acceptance.

| Minecraft | Loader | Loader-Version | Java | Schutzdatei / Protection JAR | Status |
|---|---|---|---|---|---|
| 1.20.1 | FABRIC | 0.20.1 | 17 | mcj-guard-fabric-1.20.1-1.0.7.jar | BESTANDEN |
| 1.20.1 | FORGE | 47.4.28 | 17 | mcj-guard-forge-1.20.1-1.0.7.jar | BESTANDEN |
| 1.20.1 | NEOFORGE | 47.1.106 | 17 | mcj-guard-forge-1.20.1-1.0.7.jar | BESTANDEN |
| 1.21.1 | FABRIC | 0.20.1 | 21 | mcj-guard-fabric-1.21.1-1.0.7.jar | BESTANDEN |
| 1.21.1 | FORGE | 52.1.20 | 21 | mcj-guard-forge-1.21.1-1.0.7.jar | BESTANDEN |
| 1.21.1 | NEOFORGE | 21.1.265 | 21 | mcj-guard-neoforge-1.21.1-1.0.7.jar | BESTANDEN |
| 26.3 | FABRIC | 0.20.1 | 25 | mcj-guard-fabric-26.3-1.0.7.jar | BESTANDEN |
| 26.3 | FORGE | 66.1.0 | 25 | mcj-guard-forge-26.3-1.0.7.jar | BESTANDEN |
| 26.3 | NEOFORGE | 26.3.0.99 | 25 | mcj-guard-neoforge-1.0.7.jar | BESTANDEN |

NeoForge 1.20.1 verwendet das historische offizielle Artefakt `net.neoforged:forge:1.20.1-47.1.106`. Es ist nicht mit Forge 47.4.28 austauschbar. Beide verwenden dieselbe MCJ-Schutzdatei; ihre Loader und Clientpakete bleiben unterschiedlich.

NeoForge 1.20.1 uses the historical official artefact `net.neoforged:forge:1.20.1-47.1.106`. It is not interchangeable with Forge 47.4.28. They share the MCJ protection JAR, but retain distinct loader and client-pack identities.

## Was geprüft wurde / What was tested

Für jede Kombination sind Installation und Serverstart mit der passenden Java-Laufzeit, eine echte Clientverbindung, Besucherbeschränkungen, Spielerfreigabe und Rechteentzug, Modfunktionen und Abhängigkeiten sowie Export und tatsächlicher Prism-Import des Clientpakets belegt. Dazu gehören Sicherung und Wiederherstellung, Versionswechsel mit Rückfall sowie das sichere Ablehnen ungeeigneter Konfigurationen. Alle neun Profile haben die zehn erforderlichen Prüfschritte bestanden: 90 von 90.

Die native Bedienprüfung bestätigt in jedem Profil die Reihenfolge Besucher → Spieler → Besucher: Der Testblock blieb geschützt, ließ sich nach der Freigabe abbauen und war nach dem Rechteentzug erneut geschützt. Fabric und die modernen NeoForge-Profile wurden mit Jade geprüft, Forge und NeoForge 1.20.1 mit Carry On einschließlich unverändertem Truheninhalt. 145 zusätzliche Handler-Prüfungen ergänzen diese echte Bedienung; sie werden nicht als native Clientpakete ausgegeben. Nach Entfernen der Hilfsmods starteten und stoppten alle neun Server mit ihrem regulären Mod-Bestand und Rückgabewert 0.

For each combination, the records cover installation and startup with the matching Java runtime, a real client connection, visitor restrictions, player approval and revocation, functional mods and dependencies, and client-pack export and actual Prism import. They also cover backup/restoration, version changes with rollback and rejection of unsafe configurations. All nine profiles passed their ten required checks: 90 of 90.

In every native client, the test block remained protected for a visitor, could be mined after player approval and was protected again after revocation. Fabric and modern NeoForge profiles were checked with Jade; Forge and NeoForge 1.20.1 with Carry On and an unchanged chest inventory. An additional 145 handler checks supplement actual client interaction and are not presented as native client packets. After removing helper mods, all nine servers started and stopped with their regular mods and exit code 0.

## Nachweise und Grenzen / Evidence and limits

- [Maschinenlesbare Matrix / Machine-readable matrix](../artifacts/compatibility/release-matrix.json): Versionen, Schutzdateien und Zuordnung der zehn Prüfschritte.
- [Guard-Abnahme / Guard acceptance](../artifacts/guard-acceptance-20261102.json): genau abgenommene Loader, Guard-Prüfsummen und Client-Moddateien.
- [Client- und Rollenprüfungen / Client and role checks](../artifacts/compatibility/native-client-evidence-20261102.json), [Paket- und Installationsnachweise / Pack and installation evidence](../artifacts/compatibility/native-preparation-20261102.json).
- [Wartung und Rücksicherung / Maintenance and restoration](../artifacts/compatibility/maintenance-evidence-20261102.json), [ergänzende Komponentenbelege / component evidence](../artifacts/compatibility/component-evidence.json).
- [RCON-Korrektur / RCON correction](../artifacts/compatibility/rcon-completion-20261102.json): bestätigter Abschluss leerer Antworten, vollständige mehrteilige Antworten und gezielte Regression.

Unveränderte Komponenten übernehmen ihre vorhandenen Nachweise mit den ursprünglichen Datei- und Image-Identitäten. Das bedeutet keine erneute vollständige Spielabnahme eines späteren Manager-Images. Die gemeinsame RCON-Korrektur besitzt eigene gezielte Prüfungen. Leere Forge-1.21.1-Antworten benötigen dabei gegebenenfalls das normale Vier-Sekunden-Zeitlimit; fehlende Bestätigung oder ein Verbindungsabbruch bleiben Fehler.

Evidence for unchanged components retains its original file and image identities; it does not claim a repeated full gameplay acceptance on a later manager image. The shared RCON correction has separate targeted checks. Empty Forge 1.21.1 replies may take the normal four-second deadline; missing acknowledgement or disconnection remains an error.

Die Abnahme gilt für die festgelegten Versionen und dokumentierten Moddateien. Sie garantiert keine beliebigen zusätzlichen Mods oder Loader-Patchstände. Frühere Backup-Nachweise werden nur für unveränderte Archiv- und Wiederherstellungskomponenten übernommen; die Installation und der Start der aktuellen Schutzdateien sind gesondert belegt.

Acceptance covers the pinned versions and documented mod files, not arbitrary additional mods or loader patch versions. Earlier backup records are reused only for unchanged archive/restoration components, with separate installation and startup evidence for the current protection files.

**Statusbegriffe:** BESTANDEN = alle erforderlichen Nachweise vorhanden; NICHT VERFÜGBAR = Kombination existiert nicht oder ist technisch ausgeschlossen; FEHLGESCHLAGEN = notwendige Prüfung fehlgeschlagen; NOCH NICHT GEPRÜFT = Nachweis fehlt. Ein Katalogeintrag allein genügt nie.

**Status terms:** BESTANDEN = all required evidence present; NICHT VERFÜGBAR = unavailable or technically excluded; FEHLGESCHLAGEN = required check failed; NOCH NICHT GEPRÜFT = evidence missing. A catalogue entry alone is never enough.

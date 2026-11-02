# Kompatibilitätsabnahme / Compatibility acceptance

Arbeitsstand auf Basis von f7f92af. Die Veröffentlichung bleibt gesperrt. Die Matrix unterscheidet vorhandene Katalogeinträge von tatsächlich abgenommenen Kombinationen.

## Vereinbarter Umfang / Agreed scope

Zur Freigabe vorgesehen sind genau die folgenden neun Kombinationen. Für jede gilt die genannte Java-Version. Andere Java-Kanäle und Minecraft-/Loader-Stände erhalten durch ihre Katalogverfügbarkeit keine Freigabe.

| Minecraft | Loader | Loader-Version | Java | Schutzdatei | Status |
|---|---|---|---|---|---|
| 1.20.1 | FABRIC | 0.20.1 | 17 | mcj-guard-fabric-1.20.1-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 1.20.1 | FORGE | 47.4.28 | 17 | mcj-guard-forge-1.20.1-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 1.20.1 | NEOFORGE | 47.1.106 | 17 | mcj-guard-forge-1.20.1-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 1.21.1 | FABRIC | 0.20.1 | 21 | mcj-guard-fabric-1.21.1-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 1.21.1 | FORGE | 52.1.20 | 21 | mcj-guard-forge-1.21.1-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 1.21.1 | NEOFORGE | 21.1.265 | 21 | mcj-guard-neoforge-1.21.1-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 26.3 | FABRIC | 0.20.1 | 25 | mcj-guard-fabric-26.3-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 26.3 | FORGE | 66.1.0 | 25 | mcj-guard-forge-26.3-1.0.7.jar | NOCH NICHT GEPRÜFT |
| 26.3 | NEOFORGE | 26.3.0.99 | 25 | mcj-guard-neoforge-1.0.7.jar | NOCH NICHT GEPRÜFT |

Die vorhandenen NeoForge-Funktionsnachweise bleiben erhalten. Da die Schutzdateien geändert wurden, werden die betroffenen Schutz- und Rollenprüfungen gezielt für die neuen Prüfsummen wiederholt. Bereits geprüfte, unveränderte Minecraft-, Welt- und Backup-Funktionen werden nicht erneut vollständig abgenommen. Der Gesamtstatus wird erst nach Zuordnung aller erforderlichen Nachweise gesetzt.

NeoForge 1.20.1 verwendet das historische offizielle Artefakt net.neoforged:forge:1.20.1-47.1.106. Es ist weder eine fehlende NeoForge-Version noch mit Forge 47.4.28 gleichzusetzen. Installation, tatsächlich gestarteter Loader und Clientexport müssen diese Identität erhalten.

## Bedeutung der Ergebnisse / Meaning of results

- **BESTANDEN**: Alle erforderlichen Gates sind durch konkrete Logs, Versionen und Dateiidentitäten belegt.
- **NICHT VERFÜGBAR**: Die offizielle Kombination existiert nicht oder eine belegte technische Voraussetzung schließt sie aus.
- **FEHLGESCHLAGEN**: Ein tatsächlich ausgeführter notwendiger Test ist fehlgeschlagen.
- **NOCH NICHT GEPRÜFT**: Ein notwendiger Nachweis fehlt; dies ist keine Freigabe.

The nine combinations above are the agreed release scope. Catalogue discovery is not functional acceptance. A passed verdict requires installation, the exact Java/loader runtime, a real Minecraft client connection, visitor protection, role changes, mod dependencies, client-pack export/import, backup/restore, version change/rollback and rejection of unsafe configurations. Existing evidence is reused only where identities and tested behavior match.

Die maschinenlesbare Matrix steht in [artifacts/compatibility/release-matrix.json](../artifacts/compatibility/release-matrix.json). Der vollständige offizielle Katalog mit 103 stabilen Minecraft-Versionen wurde getrennt gesichert; er erteilt keine Unterstützung für ungeprüfte Versionen.

## Bisheriger Teilnachweis / Completed checks

Die sieben neuen Kombinationen wurden zunächst mit den vorherigen Schutzdateien und leerem Serververzeichnis installiert, mit der vorgesehenen Java-Version und dem passenden Schutzmod gestartet und nach bestätigtem Speichern sauber beendet. Loader- und Moddateien sind durch Prüfsummen zugeordnet. Die frühere Fabric-Prüfung erfasste nicht alle Paketwege und gilt deshalb nicht als Schutzabnahme. Für die korrigierten Dateien liegen eigene erfolgreiche Serverstarts vor. Die vollständige Client- und Rollenprüfung steht noch aus; deshalb bleibt der Gesamtstatus offen.

The seven new combinations passed a clean server installation and startup with their previous guard files and the specified Java runtime, and a clean stop after saving. Loader and mod files are identified by their hashes. The earlier Fabric check did not cover every packet path and does not count as protection acceptance. The corrected files have their own successful server-start checks. Full client and role acceptance is still pending, so the overall status remains open.

## Geprüfte Wartungsschritte / Verified maintenance steps

Am 2. November 2026 wurde die folgende serverseitige Kette über die normale Warteschlange geprüft:

| Schritt | Minecraft | Loader | Java | Ergebnis |
|---|---|---|---|---|
| Ausgangsstand | 1.20.1 | Forge 47.4.28 | 17 | Gesichert |
| Wechsel | 1.20.1 | NeoForge 47.1.106 | 17 | BESTANDEN |
| Wechsel mit eigener Welt | 1.21.1 | Fabric 0.20.1 | 21 | BESTANDEN |
| Wechsel mit eigener Welt | 26.3 | Forge 66.1.0 | 25 | BESTANDEN |
| Rücksicherung des Ausgangsstands | 1.20.1 | Forge 47.4.28 | 17 | BESTANDEN |

Die Wechsel wurden jeweils zuerst ohne Netzwerk und anschließend durch die reguläre Übernahme geprüft. Nach der Rücksicherung stimmten die ursprüngliche Laufzeit, die Mod-Prüfsummen und der gespeicherte Welt-Testwert wieder überein. Der Testserver wurde sauber gestoppt. Die Zwischenstände wurden in dieser Kette nicht jeweils aus ihrer eigenen Sicherung wiederhergestellt.

Zusätzlich wurden vier Sperren über die echte Manager-API geprüft: abgeschaltete Online-Authentifizierung, Java 17 für Minecraft 26.3, eine nicht vorhandene Loader-Version und ein Katalogeintrag ohne passenden Guard. Diese Versuche änderten weder den aktiven Stand noch starteten sie den Spielserver.

Das sind einzelne Wartungsnachweise. Die neun Gesamtprofile bleiben bis zum Abschluss aller erforderlichen Prüfungen **NOCH NICHT GEPRÜFT**. Insbesondere ersetzen diese Schritte keine echte Clientverbindung und keine Besucher- oder Rollenprüfung.

The server-side sequence above passed through the normal manager queue, including offline candidate checks and restoration of the original runtime, mod hashes and world marker. It does not claim separate restores of every intermediate backup. Four unsafe configuration attempts were also rejected without starting Minecraft or changing the active state. These results cover individual maintenance gates; all nine overall profiles still require the remaining client and permission checks.

Die Datei [server-maintenance.json](../artifacts/compatibility/server-maintenance.json) enthält die genauen Loader-, Guard- und Image-Identitäten. Die [maschinenlesbare Matrix](../artifacts/compatibility/release-matrix.json) ordnet die bestandenen Teilschritte den Profilen zu.

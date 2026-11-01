# Kompatibilitätsabnahme / Compatibility acceptance

Arbeitsstand auf Basis von f7f92af. Die Veröffentlichung bleibt gesperrt. Die Matrix unterscheidet vorhandene Katalogeinträge von tatsächlich abgenommenen Kombinationen.

## Vereinbarter Umfang / Agreed scope

Zur Freigabe vorgesehen sind genau die folgenden neun Kombinationen. Für jede gilt die genannte Java-Version. Andere Java-Kanäle und Minecraft-/Loader-Stände erhalten durch ihre Katalogverfügbarkeit keine Freigabe.

| Minecraft | Loader | Loader-Version | Java | Schutzdatei | Status |
|---|---|---|---|---|---|
| 1.20.1 | FABRIC | 0.20.1 | 17 | mcj-guard-fabric-1.20.1-1.0.6.jar | NOCH NICHT GEPRÜFT |
| 1.20.1 | FORGE | 47.4.28 | 17 | mcj-guard-forge-1.20.1-1.0.6.jar | NOCH NICHT GEPRÜFT |
| 1.20.1 | NEOFORGE | 47.1.106 | 17 | mcj-guard-forge-1.20.1-1.0.6.jar | NOCH NICHT GEPRÜFT |
| 1.21.1 | FABRIC | 0.20.1 | 21 | mcj-guard-fabric-1.21.1-1.0.6.jar | NOCH NICHT GEPRÜFT |
| 1.21.1 | FORGE | 52.1.20 | 21 | mcj-guard-forge-1.21.1-1.0.6.jar | NOCH NICHT GEPRÜFT |
| 1.21.1 | NEOFORGE | 21.1.265 | 21 | mcj-guard-neoforge-1.21.1-1.0.5.jar | NOCH NICHT GEPRÜFT |
| 26.3 | FABRIC | 0.20.1 | 25 | mcj-guard-fabric-26.3-1.0.6.jar | NOCH NICHT GEPRÜFT |
| 26.3 | FORGE | 66.1.0 | 25 | mcj-guard-forge-26.3-1.0.6.jar | NOCH NICHT GEPRÜFT |
| 26.3 | NEOFORGE | 26.3.0.99 | 25 | mcj-guard-neoforge-1.0.5.jar | NOCH NICHT GEPRÜFT |

Die beiden vorhandenen NeoForge-Guard-Abnahmen bleiben anerkannt. Der Status in dieser neuen Gesamtmatrix wird erst gesetzt, wenn auch die übrigen Funktionsnachweise eindeutig dieser Kombination zugeordnet sind. Vorhandene Nachweise werden nur für unveränderte Dateiidentitäten und dieselben geprüften Funktionen übernommen.

NeoForge 1.20.1 verwendet das historische offizielle Artefakt net.neoforged:forge:1.20.1-47.1.106. Es ist weder eine fehlende NeoForge-Version noch mit Forge 47.4.28 gleichzusetzen. Installation, tatsächlich gestarteter Loader und Clientexport müssen diese Identität erhalten.

## Bedeutung der Ergebnisse / Meaning of results

- **BESTANDEN**: Alle erforderlichen Gates sind durch konkrete Logs, Versionen und Dateiidentitäten belegt.
- **NICHT VERFÜGBAR**: Die offizielle Kombination existiert nicht oder eine belegte technische Voraussetzung schließt sie aus.
- **FEHLGESCHLAGEN**: Ein tatsächlich ausgeführter notwendiger Test ist fehlgeschlagen.
- **NOCH NICHT GEPRÜFT**: Ein notwendiger Nachweis fehlt; dies ist keine Freigabe.

The nine combinations above are the agreed release scope. Catalogue discovery is not functional acceptance. A passed verdict requires installation, the exact Java/loader runtime, a real Minecraft client connection, visitor protection, role changes, mod dependencies, client-pack export/import, backup/restore, version change/rollback and rejection of unsafe configurations. Existing evidence is reused only where identities and tested behavior match.

Die maschinenlesbare Matrix steht in [artifacts/compatibility/release-matrix.json](../artifacts/compatibility/release-matrix.json). Der vollständige offizielle Katalog mit 103 stabilen Minecraft-Versionen wurde getrennt gesichert; er erteilt keine Unterstützung für ungeprüfte Versionen.

## Bisheriger Teilnachweis / Completed checks

Die sieben neuen Kombinationen wurden mit leerem Serververzeichnis installiert, mit der vorgesehenen Java-Version und dem passenden Schutzmod gestartet und nach bestätigtem Speichern sauber beendet. Loader- und Moddateien sind durch Prüfsummen zugeordnet. Bei Fabric wurde zusätzlich geprüft, dass die Besuchersperre vor der Mod-Schnittstelle ausgeführt wird. Die echten Client- und Rollenprüfungen stehen noch aus; deshalb bleibt der Gesamtstatus offen.

The seven new combinations passed a clean server installation, startup with the specified Java runtime and guard, and a clean stop after saving. Loader and mod files are identified by their hashes. Fabric also passed the check that visitor protection runs before mod packet handlers. Real client and role checks are still pending, so these startup results do not constitute full acceptance.

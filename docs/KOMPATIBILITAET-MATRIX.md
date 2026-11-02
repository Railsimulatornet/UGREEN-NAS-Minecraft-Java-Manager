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

## Zugeordnete Teilergebnisse / Recorded component results

Die folgende Übersicht nennt bereits belegte Teilschritte. „Offen“ bedeutet, dass die Zuordnung für den aktuellen Stand noch nicht abgeschlossen ist. Es bedeutet nicht, dass jeder frühere Test wiederholt werden muss. Alle neun Gesamtprofile bleiben offen.

| Minecraft / Loader | Installation | Serverstart / Startup | Paketimport / Pack import | Rücksicherung / Restore | Versionswechsel / Version change |
|---|---|---|---|---|---|
| 1.20.1 / FABRIC | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed |
| 1.20.1 / FORGE | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed |
| 1.20.1 / NEOFORGE | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed |
| 1.21.1 / FABRIC | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed |
| 1.21.1 / FORGE | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed |
| 1.21.1 / NEOFORGE | Offen / Pending | Bestanden / Passed | Offen / Pending | Bestanden / Passed | Bestanden / Passed |
| 26.3 / FABRIC | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed |
| 26.3 / FORGE | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed | Bestanden / Passed |
| 26.3 / NEOFORGE | Offen / Pending | Bestanden / Passed | Offen / Pending | Bestanden / Passed | Bestanden / Passed |

Bei sieben Profilen passen Minecraft, Java, Loader-Datei und Image weiterhin zur früheren sauberen Installation. Dazu sind die Installation und der erfolgreiche Start des aktuellen Guards über den normalen Managerablauf belegt. Diese Nachweise werden gemeinsam übernommen; eine weitere Neuinstallation wurde dafür nicht durchgeführt. Für die beiden übrigen NeoForge-Profile ist der Start mit dem aktuellen Guard belegt. Die Zuordnung der übrigen Installationsnachweise bleibt dort offen.

Sieben exportierte Clientpakete wurden bereits tatsächlich in Prism importiert. Minecraft-, Loader- und Mod-Prüfsummen sind zugeordnet. Der Paketimport bestätigt noch keine Verbindung zum Server und keine funktionierenden Mod-Aktionen. Diese Prüfungen sowie Besucherrechte und Rechteentzug bleiben getrennt offen.

Frühere Sicherungs- und Wiederherstellungsläufe mit älteren Guard-Dateien bleiben als Nachweise erhalten. Sie werden nicht als vollständige Abnahme der neuen Schutzdateien ausgegeben. Die beiden gesonderten NeoForge-Startproben wurden nach erfolgreichem Start per Signal beendet (Prozess-Rückgabewert 143); daraus wird kein erfolgreicher normaler Manager-Stopp abgeleitet.

The table records component evidence, not full profile acceptance. Seven unchanged clean Java/loader installations are combined with verified installation and startup of the current guard through the normal manager. The other two NeoForge profiles have current-guard startup evidence; their remaining installation records still need to be matched. Seven actual Prism imports are verified by their Minecraft, loader and mod identities. Server connections, mod actions, visitor restrictions and role revocation remain separate checks. Historical backups retain their earlier guard identities. The two separate NeoForge startup probes ended with signal exit 143 and do not prove a normal manager shutdown.

Die genauen Identitäten, Prüfsummen und Grenzen stehen in [component-evidence.json](../artifacts/compatibility/component-evidence.json). / Exact identities, hashes and scope limits are recorded in [component-evidence.json](../artifacts/compatibility/component-evidence.json).

## Ergänzende Wartungsnachweise / Additional maintenance evidence

Die noch fehlenden serverseitigen Versionswechsel nach Fabric 1.20.1, Forge 1.21.1, NeoForge 1.21.1, NeoForge 26.3 und Fabric 26.3 sind geprüft. Jeder Wechsel wurde mit seinem konkreten Plan zuerst isoliert geprüft und danach regulär übernommen. Am Ende der beiden Prüfketten wurde jeweils der ursprüngliche Forge-1.20.1-Stand wiederhergestellt. Laufzeit, Mod-Prüfsummen und Welt-Testwert stimmten nach der Rückkehr wieder überein; der Testserver wurde sauber beendet. Die schon vorher belegten Übergänge nach NeoForge 1.20.1, Fabric 1.21.1 und Forge 26.3 wurden dafür nicht erneut ausgeführt.

Für NeoForge 1.21.1 und 26.3 sind außerdem eigene Sicherungen mit Guard 1.0.7, die isolierte Wiederherstellungsprüfung und die tatsächliche Rücksicherung belegt. Der Welt-Testwert wurde jeweils von 17 auf 29 geändert und anschließend aus der Sicherung wieder auf 17 gesetzt. Der bereits vorhandene Nachweis für Fabric 26.3 mit demselben aktuellen Guard wird übernommen.

Die sechs früheren Sicherungsnachweise bleiben mit ihren damaligen Guard-Prüfsummen erhalten. Ihre Archiv-, Extraktions- und Wiederherstellungskomponenten sind im Quellvergleich unverändert. Die Installation und der Start des aktuellen Guards sowie die geänderte gemeinsame Vorbereitung und das Beenden des Servers sind getrennt belegt. Deshalb wird der bereits geprüfte Sicherungsablauf wiederverwendet; ein neuer vollständiger Rücksicherungslauf wird für diese sechs Fälle nicht behauptet. Die Prüfung der Besucherrechte bleibt davon unabhängig offen.

Der ausgelieferte Startschutz wurde für alle neun Kombinationen mit gültiger, fehlender und veränderter Guard-Datei geprüft: 27 bestandene Fälle. Eine gültige Datei erreichte den vorbereiteten Prüfendpunkt; fehlende oder veränderte Dateien wurden vorher blockiert. Dieser Prüfendpunkt ersetzt den Minecraft-Start und bestätigt ausschließlich die Prüfsummensperre. Die vier zuvor geprüften gemeinsamen Planungssperren bleiben zusätzlich erhalten.

The five previously missing server-side version transitions passed their mandatory isolated plan checks and normal promotion. Both test sequences ended by restoring the original Forge 1.20.1 runtime, mod hashes and world marker, followed by a clean stop. The previously recorded transitions to NeoForge 1.20.1, Fabric 1.21.1 and Forge 26.3 were reused.

NeoForge 1.21.1 and 26.3 also passed their own backup and restore sequences with Guard 1.0.7: the world marker changed from 17 to 29 and returned to 17 after restoration. The existing Fabric 26.3 proof uses the same current guard. Six earlier backup proofs are reused for unchanged archive and restoration components, with separate evidence for current-guard installation/startup and the changed shared preparation/shutdown paths. Their earlier guard identities remain visible; no new full roundtrip is claimed for those six cases.

All 27 checksum-gate cases passed across the nine combinations. Missing and modified guards were blocked before a harmless sentinel; a valid guard reached it. This checks the shipped startup gate without launching Minecraft. The four existing common planning-rejection checks remain valid. Visitor enforcement, role changes, actual client connections and functional mod acceptance are still separate requirements.

Die Zuordnung und die Prüfsummen stehen in [maintenance-evidence-20261102.json](../artifacts/compatibility/maintenance-evidence-20261102.json). Alle neun Gesamtprofile bleiben **NOCH NICHT GEPRÜFT**; die Veröffentlichung bleibt gesperrt. / Exact identities and hashes are recorded in the linked evidence file. All nine complete profiles remain unapproved, and publication remains blocked.

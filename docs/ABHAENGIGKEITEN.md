# Abhängigkeiten aktualisieren

Dependabot prüft Python-Pakete, Docker-Basisimages und GitHub-Aktionen wöchentlich.

Kleine Python-Korrekturen können nach erfolgreichen Prüfungen automatisch übernommen werden. Das gilt zunächst für AnyIO, Pydantic, pydantic-core, python-multipart und typing-inspection. Nur die beiden Versionslisten dürfen sich ändern; Haupt- und Nebenversion müssen gleich bleiben.

Vor einer Übernahme müssen die Python-/JavaScript-Tests, alle acht Guard-Builds, die CodeQL-Prüfungen und der Image-Build für den genauen PR-Commit erfolgreich abgeschlossen sein. Der Image-Build prüft auch Trivy sowie Aktualisierung und Rückfall in einer isolierten Testinstallation. Fehlgeschlagene, fehlende, übersprungene oder noch laufende Pflichtprüfungen verhindern die Übernahme. Ein geänderter PR-Stand wird erneut geprüft. Der Branch muss den geprüften main-Stand enthalten; der Branchschutz bleibt wirksam.

Pull Requests mit Programm- oder Abhängigkeitsänderungen bauen das Prüfimage automatisch. Nach einer automatischen Übernahme werden Image- und CodeQL-Prüfung ausdrücklich für den Merge-Commit angefordert. Hat sich main inzwischen verändert, bricht die Nachprüfung ab. Ein erfolgreicher Übernahmeschritt allein gilt nicht als abgeschlossene Nachprüfung.

Größere Versionsschritte, unbekannte Pakete sowie Docker- und Workflow-Änderungen werden weiterhin einzeln geprüft. Der manuelle Lauf der Patchupdate-Automatik zeigt nur das Ergebnis an und führt keine Zusammenführung durch.

Eine Übernahme auf GitHub aktualisiert weder die NAS-Installation noch das veröffentlichte Docker-Image. Veröffentlichung und Produktivübernahme erfolgen weiterhin getrennt.

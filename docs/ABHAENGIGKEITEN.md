# Abhängigkeiten aktualisieren

Dependabot prüft Python-Pakete, Docker-Basisimages und GitHub-Aktionen wöchentlich.

Kleine Python-Korrekturen können nach erfolgreichen Prüfungen automatisch übernommen werden. Das gilt zunächst für AnyIO, Pydantic, pydantic-core, python-multipart und typing-inspection. Nur die beiden Versionslisten dürfen sich ändern; Haupt- und Nebenversion müssen gleich bleiben.

Vor einer Übernahme müssen die Python-/JavaScript-Tests, alle acht Guard-Builds und die CodeQL-Prüfungen für denselben Commit erfolgreich abgeschlossen sein. Fehlgeschlagene, fehlende oder noch laufende Prüfungen verhindern die Übernahme. Ein geänderter PR-Stand wird erneut geprüft. Der Branchschutz bleibt wirksam.

Größere Versionsschritte, unbekannte Pakete sowie Docker- und Workflow-Änderungen werden weiterhin einzeln geprüft. Der manuelle Lauf der Patchupdate-Automatik zeigt nur das Ergebnis an und führt keine Zusammenführung durch.

Eine Übernahme auf GitHub aktualisiert weder die NAS-Installation noch das veröffentlichte Docker-Image. Veröffentlichung und Produktivübernahme erfolgen weiterhin getrennt.

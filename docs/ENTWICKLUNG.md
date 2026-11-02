# Quellcode und neue Versionen / Source and new versions

[Deutsch](#deutsch) · [English](#english)

## Deutsch

Diese Seite richtet sich an Entwickler und Projektbetreuer. Für die normale NAS-Installation verwende die [Installationsanleitung](INSTALLATION-DE.md), für spätere Manager-Updates [AKTUALISIEREN.md](AKTUALISIEREN.md).

### Ordnerstruktur

| Ordner oder Datei | Inhalt |
| --- | --- |
| `mcj/` | Manager, Steuerungsdienst, Anmeldung und Wartungsaufträge. |
| `mcj/static/` | Weboberfläche, Sprachtexte, Schrift und Grafiken. |
| `mcj/client_pack_resources/` | Client-Anpassungen, passende Quellen und Fremdlizenzen. |
| `tools/` | Einrichtung, Manager-Update und Zugangswiederherstellung. Diese Werkzeuge können NAS-Dienste und Daten verändern. |
| `deploy/` | UGOS-Vorlagen für Erstinstallation und Manager-Updates. |
| `artifacts/` | Die acht ausgelieferten MCJ-Schutzdateien für neun Fabric-/Forge-/NeoForge-Kombinationen mit Prüfsummen, Lizenzen und genau begrenzten Kompatibilitätsnachweisen. |
| `licenses/` | Originale Lizenz- und Hinweistexte zusätzlich mitgelieferter Werkzeuge. |
| `guard-fabric-1201/`, `guard-fabric-1211/`, `guard-fabric-263/` | Fabric-Guards für die drei unterstützten Minecraft-Versionen. |
| `guard-forge-1201/`, `guard-forge-1211/`, `guard-forge-263/` | Forge-Guards; die 1.20.1-Datei wird auch mit NeoForge 47.1.106 verwendet. |
| `guard-neoforge/` | NeoForge-Guard für Minecraft 26.3. |
| `guard-neoforge-1211/` | Guard-Quellcode für Minecraft 1.21.1. |
| `tests/` | Automatische Prüfungen und gesonderte Abnahmeskripte. |
| `docs/` | Anleitungen, PDF-Handbücher, Bilder, Kompatibilität und Lizenzinformationen. |
| `.github/` | Automatische Prüfungen, manuell gestarteter Image-Bau und Upload. |
| `compose.yaml` | Vorlage für das vom Einrichtungsprogramm erzeugte Dienstprojekt. Pfade und Werte werden bei der Einrichtung angepasst. Für die normale UGOS-Installation verwende `deploy/ugos-einrichtung.yaml`. |
| `Dockerfile` | Bauanleitung für das Manager-Image. Minecraft verwendet ein separates Image. |

### Lokale Prüfungen

Verwende Python 3.12 in einer eigenen virtuellen Umgebung. JavaScript-Prüfungen verwenden den eingebauten Testläufer von Node.js.

```sh
python -m venv .venv
# Linux/macOS: . .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/*.test.cjs
```

`pytest` führt die normalen `test_*.py`-Prüfungen aus. Die gesonderten `acceptance_*.py`-Skripte und `native_app_update.py` können Docker und isolierte Testdienste benötigen. Lies ihre Voraussetzungen, bevor du sie startest. Sie gehören nicht auf eine laufende NAS-Installation.

Der erste Repository-Commit wird vollständig automatisch geprüft. Für spätere reine Textänderungen genügen die betroffenen Sprach-, Link- und Dokumentationsprüfungen. Funktionsänderungen benötigen passende Regressionstests. Bereits abgeschlossene Spiel- oder NAS-Abnahmen müssen wegen einer Textkorrektur nicht wiederholt werden.

Die Guard-Builds verwenden die in `.github/workflows/image.yml` festgelegten Umgebungen. Eine Quellcodeänderung am Guard benötigt einen neuen Build und passende Nachweise für das neue JAR. Der Nachweis für eine alte Prüfsumme gilt nicht automatisch für eine neue Datei.

### Versionsnummern und Docker-Images

Die Manager-Version steht in `mcj/__init__.py`. Der Image-Bau liest sie dort aus. Halte README, Changelog, `Dockerfile`, die Versionsanzeige und die Installationsvorlage im Einklang. `tests/test_release_metadata.py` prüft diese Angaben. Ein Git-Tag `v1.0.1` darf nur auf Code mit der Manager-Version `1.0.1` zeigen. Minecraft, Java, Modloader und Guard besitzen eigene Versionsnummern.

| Image-Tag | Bedeutung |
| --- | --- |
| `1.0.0`, später zum Beispiel `1.0.1` | Festgehaltene Veröffentlichung. Nach öffentlicher Freigabe nicht durch anderen Inhalt ersetzen. Eine Korrektur erhält eine neue Versionsnummer. |
| `stable` | Zuletzt freigegebene Version für den UGOS-Updateweg. |
| `edge` | Optionaler Entwicklungsstand von `main`, kein Ersatz für `stable`. |
| `sha-<vollständiger Commit>` | Zuordnung zu einem bestimmten Quellstand. |

Ein Registry-Digest identifiziert den Inhalt unabhängig vom Tag. Sichere zu jeder Veröffentlichung Commit, Versionsnummer, Image-ID, Registry-Digest und Prüfergebnisse. Versionsnummer und `stable` müssen auf denselben freigegebenen Inhalt zeigen. Verwende in Docker Hub nach Möglichkeit unveränderliche Regeln für Versions- und Commit-Tags; `stable` und `edge` bleiben verschiebbar.

1. Prüfe die Änderungen und die dafür notwendigen Tests. Aktualisiere Changelog und Dokumentation. Installationstexte müssen mit beiden PDFs und `docs/handbooks.json` übereinstimmen.
2. Starte **Actions → Tests und Docker-Image → Run workflow** am endgültigen Quellstand mit `build_image=true` und `publish_image=false`. `full_validation=true` erzwingt die vollständige Prüfung, wenn die Änderung dies erfordert. Prüfe auch den vollständigen Image-Bericht. Ein erfolgreicher Bau bedeutet nicht, dass sämtliche gemeldeten Schwachstellen behoben sind.
3. Nach Freigabe kann der Workflow mit `publish_image=true` gestartet werden. Er baut einen neuen Kandidaten, prüft ihn und überträgt genau das Image aus diesem Lauf. Er verwendet keinen früheren Bau ungeprüft weiter. `installation_tags=true` setzt zusätzlich Versionsnummer und `stable`. Versions- und Revisionslabel werden vor dem Upload abgeglichen. Ein Push, Pull Request oder neuer Git-Tag allein lädt kein Image hoch.
4. Prüfe die tatsächlichen Registry-Digests und die öffentliche Erreichbarkeit. Der separate Lauf mit `anonymous_installation=true`, `publish_image=false`, vollständigem `expected_revision` und dem Registry-`expected_digest` lädt Versions-Tag und `stable` auf einem frischen Runner ohne Anmeldung. Er startet keinen NAS-Einrichtungsauftrag und ersetzt keine NAS-Installationsabnahme.
5. Veröffentliche den passenden Git-Tag und die Release-Notizen nach der vorgesehenen Freigabe. GitHub- und Docker-Hub-Sichtbarkeit sind gesonderte Einstellungen. Aktiviere bei der öffentlichen Bereitstellung den privaten GitHub-Meldeweg für Sicherheitsprobleme und prüfe dessen Erreichbarkeit.

Das Manager-Image wird für `linux/amd64` gebaut; ARM-Systeme werden nicht unterstützt. Minecraft verwendet ein separates `itzg/minecraft-server`-Image. Ein Manager-Update ersetzt weder dieses Spiel-Image noch Welt und Mods. Der NAS-Updater prüft die bestehende Compose-Identität, sichert die Manager-Datenbank und stellt bei einer fehlgeschlagenen Übernahme den vorherigen App-Stand wieder her. Behalte Rückfall-Images und private Sicherungen, bis das Update bestätigt ist. Allgemeine Docker-Aufräumaktionen gehören nicht zum Updateweg.

Eigener Projektcode steht unter [MIT](../LICENSE), Fremdkomponenten behalten ihre [eigenen Lizenzen](LIZENZEN.md).

### Abhängigkeiten pflegen

Dependabot prüft Python-Pakete, Docker-Basisimages und GitHub-Actions wöchentlich. Vorschläge werden je Bereich gebündelt; es bleibt höchstens ein Versionsupdate-PR je Bereich gleichzeitig offen. Das übernimmt keine Änderung automatisch. Prüfe Versionshinweise, Kompatibilität und die automatischen Tests vor dem Zusammenführen. Ein zusammengeführter Vorschlag veröffentlicht kein Image und aktualisiert kein NAS.

Für Sicherheitsmeldungen gilt der [vertrauliche Meldeweg](../.github/SECURITY.md). Schütze `main` nach Möglichkeit durch erfolgreiche Prüfungen und Pull Requests, und sperre Force-Pushes sowie das Löschen des Zweigs. Bei einem einzelnen Projektbetreuer ist keine zusätzliche fremde Freigabe erforderlich.

Der veröffentlichte Image-Digest wird außerdem wöchentlich geprüft. Bericht, bekannte Paketbefunde und der Meldeweg für neue erhebliche Ergebnisse sind unter [Image-Prüfung](security/IMAGE-SECURITY.md) beschrieben. Die Prüfung verändert keine NAS-Installation.

## English

This page is for developers and maintainers. For normal NAS installation, use the [installation guide](INSTALLATION-EN.md); for later manager updates, use [the update guide](AKTUALISIEREN.md#english).

### Source layout and tests

`mcj/` contains the application and controller; `mcj/static/` contains the interface and translations. `tools/` contains setup, update and recovery tools that can change NAS services and data. `deploy/` contains the UGOS templates. `artifacts/` contains eight MCJ protection JARs for the nine supported Fabric/Forge/NeoForge combinations, with checksums, licences and scoped compatibility records. Fabric and Forge sources are in their respective `guard-fabric-*` and `guard-forge-*` folders. NeoForge sources are in `guard-neoforge/` for Minecraft 26.3 and `guard-neoforge-1211/` for Minecraft 1.21.1; NeoForge 1.20.1 uses the Forge 1.20.1 protection JAR. `tests/` contains automated tests and separate acceptance scripts, `docs/` contains guides and manuals, and `.github/` contains the workflows. Client modifications, corresponding sources and licences are in `mcj/client_pack_resources/`.

`licenses/` contains original licence and notice files for additional bundled tools.

The root `compose.yaml` is an input template for the setup program, which adjusts paths and settings. For normal UGOS installation, use `deploy/ugos-einrichtung.yaml`. The `Dockerfile` builds the manager image; Minecraft uses a separate image.

Use Python 3.12 in a dedicated virtual environment, install `requirements-dev.txt`, and run the commands above. `pytest` collects `test_*.py`; it does not automatically run `acceptance_*.py` or `native_app_update.py`. Those scripts may require Docker and isolated services. Read their requirements and keep them away from a live NAS installation.

The initial repository commit receives full automated validation. Use the relevant language, link and documentation checks for later text-only changes. Functional changes need suitable regression tests. A text correction does not require repeating completed gameplay or NAS acceptance tests. A changed Guard requires a new build and appropriate evidence for that exact JAR; acceptance for an old checksum does not transfer to a different file. Guard build environments are pinned in `.github/workflows/image.yml`.

### Versions and image publication

The manager version is defined in `mcj/__init__.py`; the image workflow reads it there. Keep the README, changelog, Dockerfile default, interface version and installation template aligned. `tests/test_release_metadata.py` checks them. A Git tag such as `v1.0.1` must match manager version `1.0.1`. Minecraft, Java, mod loaders and Guard have separate versions.

Version tags such as `1.0.0` record a release and must not be replaced with different contents after public release. Fixes receive a new version. `stable` follows the latest approved release, `edge` is an optional development build, and `sha-<full commit>` identifies a source revision. Record the commit, image ID, registry digest and checks for every release. Version and `stable` tags must refer to the same approved contents. Where available, configure immutable Docker Hub rules for version and commit tags, leaving `stable` and `edge` movable.

Run **Actions → Tests und Docker-Image → Run workflow** with `build_image=true` and `publish_image=false` first. Review the relevant tests and full image report; a successful build does not mean every vulnerability is fixed. Use `full_validation=true` when the change requires the full checks. Keep installation guides, PDFs and `docs/handbooks.json` aligned.

After approval, a run with `publish_image=true` builds and checks a new candidate and uploads that exact run's image. It does not silently reuse an older build. `installation_tags=true` also updates version and `stable` tags. The workflow checks version and revision labels before uploading. Pushes, pull requests and Git tags alone cannot upload an image.

Once available, run the separate anonymous check with `anonymous_installation=true`, `publish_image=false`, and the expected full revision and registry digest. It pulls both current-version and `stable` tags on a fresh runner without logging in. It does not start NAS setup or replace NAS installation acceptance. Publish the matching Git tag and release notes after approval. Repository and registry visibility are separate settings. Enable GitHub private vulnerability reporting when making the project public and verify that the reporting form is reachable.

The manager image supports `linux/amd64`, not ARM. Minecraft uses a separate `itzg/minecraft-server` image, which manager updates leave unchanged along with worlds and mods. The NAS updater checks the existing Compose identity, backs up the manager database and restores the previous app state if the update fails. Keep rollback images and private backups until confirmed; broad Docker cleanup is not part of this procedure.

Project-owned code uses [MIT](../LICENSE); third-party components retain [their own licences](LIZENZEN.md#english).

Dependabot checks Python packages, Docker base images and GitHub Actions weekly, grouping proposals within each ecosystem and limiting each to one open version-update PR. Updates are not merged automatically. Review release notes, compatibility and test results before merging. A merged proposal neither publishes an image nor updates a NAS. Use the [confidential reporting channel](../.github/SECURITY.md#english) for security issues. Where available, protect `main` with passing checks and pull requests, block force pushes and deletion, and avoid requiring a second reviewer for a single-maintainer project.

The published image digest also receives a weekly scan. See [Image security](security/IMAGE-SECURITY.md#english) for reports, known package findings and notification of new significant results. The scan changes no NAS installation.

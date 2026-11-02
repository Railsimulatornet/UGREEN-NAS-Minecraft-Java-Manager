# Gezielte Guard-Prüfungen

Die Hilfsmod wird ausschließlich auf einem getrennten Testserver verwendet. Sie
gehört weder in ein Clientpaket noch in eine normale Serverinstallation. Für die
Prüfung muss ein echter Minecraft-Client mit passender Version angemeldet sein.
Ohne eine ausdrücklich angelegte Prüfdatei führt die Hilfsmod keine Aktionen aus.

`build_probe_sources.py` erzeugt die Bauverzeichnisse außerhalb des Projekts. Es
verwendet die jeweiligen Guard-Bauvorlagen und Minecraft-Zuordnungen. Die dort
erzeugten Module lassen sich mit derselben Java-Version wie ihr Guard bauen.

Der Testserver erhält die Hilfsmod zusätzlich zum zu prüfenden Guard. Eine Datei
`/mcj-control/reports/probe-plan.json` wählt genau einen Fall aus:

```json
{"id":"eindeutiger-testlauf","uuid":"UUID-DES-ANGEMELDETEN-TESTSPIELERS","visitor":true,"action":"book_sign"}
```

Das Ergebnis steht in `probe-result.json`. Für jeden Fall werden Besucher und
freigegebene Spieler gegenübergestellt. Rollenwechsel erfolgen über den Manager.

| Fall | Geprüfter Weg |
| --- | --- |
| `book_sign` | Buchpaket einschließlich asynchroner Textfilterung und Signierung |
| `book_commit` | Abschließende Signierung nach einer möglichen Rollenänderung |
| `creative_slot` | Creative-Inventarpaket vor der nächsten Spielmodus-Korrektur |
| `payload` | Weiterleitung eines Mod-Pakets durch den tatsächlichen Listener |
| `payload_alt` | Derselbe Weg mit einer zweiten Paketkennung |
| `payload_brand` | Die ausdrücklich erlaubte Vanilla-Brand-Nachricht, auch als Besucher |
| `mining` | Abbau-Aufruf vor Mod-Callbacks im Spielmodus-Handler |
| `attack` | Direkter Angriff vor Mod-Callbacks, einschließlich Aufrufen ohne Angriffspaket |
| `camera` | Zuschauer-Kamera auf ein eigenes Prüftier in Minecraft 1.20.1 und 1.21.1 |

Die letzten beiden Zähler prüfen die neuen Fabric-/Forge-Einstiegspunkte. Bei den
bisherigen NeoForge-Varianten werden die neu geänderten Buch- und Inventarwege
geprüft; deren vorhandene Ereignisprüfungen sind andere Einstiegspunkte.

Die Payload-Zähler sitzen hinter dem Guard und vor der Loader-Weiterleitung.
Sie müssen bei freigegebenen Spielern erreichbar sein; ein Zähler, der auch bei
dieser Gegenprobe null bleibt, ist kein gültiger Schutzbeleg. Der Test belegt
diese Eingangsgrenze, keinen vollständigen Ablauf eines registrierten Mod-Handlers.
Die normale Mod-Kommunikation benötigt deshalb zusätzlich eine Gegenprobe mit
dem passenden Client und der tatsächlich verwendeten Mod. Minecraft 1.20.1 wird
über den Paketwrapper aufgerufen; nach dessen Rückkehr muss der Puffer genau
einmal freigegeben sein.

Die Hilfsmod hält die gezählten Aufrufe an, damit die Gegenprobe keinen Schaden
verursacht. Die Buch- und Inventarprüfungen stellen den vorherigen Inventarplatz
wieder her. Nach der Prüfung werden Prüfdatei und Hilfsmod entfernt. Anschließend
wird der Server mit dem regulären Mod-Bestand gestartet. Die ursprüngliche
Dateiidentität, der korrigierte Guard und die erlaubte Gegenprobe werden jeweils
im Prüfnachweis festgehalten.

Ein absichtlich fehlgeschlagener Vorher-Lauf belegt den Fehler und zählt nicht
als Abnahme. Nur der korrigierte Stand darf alle vorgesehenen Prüfungen bestehen.

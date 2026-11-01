# Create-Zugkorrektur 1.0.5 / Create train correction 1.0.5

## Deutsch

Diese Client-Ergänzung erhält die eigene Bewegungsinterpolation von Create für Fahrer, Mitfahrer und Zuschauer außerhalb des Zuges. Die ruhige Bewegung mit echten Clients wurde am 01.11.2026 bestätigt. Die ausgelieferte JAR ist bytegleich mit der bestätigten Datei; die [Dateizuordnung](acceptance.json) hält Prüfsumme und Umfang fest.

Unterstützt werden ausschließlich Minecraft 26.3, NeoForge 26.3.0.99, Java 25 und die beiden im [übergeordneten Hinweis](../README.md) genannten Create-Adapted-Dateien. Entferne ältere Versionen dieser Client-Ergänzung vor dem Start. Installiere sie nicht auf dem dedizierten Minecraft-Server.

Initialisierung, entfernte oder entgleiste Züge und volle Positionsabgleiche über 64 Blöcke bleiben eigene Wiederherstellungswege. Serverberechtigungen, ausgehende Pakete und ausdrückliche Teleport-/Fahrzeugpakete werden nicht verändert. Die Prüfung ist keine Freigabe anderer Minecraft-, NeoForge- oder Create-Versionen.

`build.py` benötigt die passenden, bereits vorhandenen NeoForge-/Minecraft-Bibliotheken, ein JDK 25, die passende Create-Datei und die JetBrains-Annotations-JAR 26.0.2. Es lädt keine Dateien herunter:

```sh
python build.py --libraries /path/to/libraries --jdk /path/to/jdk25 --create /path/to/create.jar --annotations /path/to/annotations-26.0.2.jar --output-dir build
```

`verify.py` vergleicht zwei unabhängige Builds und prüft die kompilierten Helfer, Fahrer-/Zuschauerfälle und die betroffenen Minecraft-/Create-Methoden. Die 40 Prüfungen ergänzen die tatsächliche Fahrtbestätigung. Die Protokollausgabe ist auf zwölf Meldungen begrenzt.

## English

This client companion preserves Create's own movement interpolation for drivers, passengers and observers outside the train. Smooth movement with actual clients was confirmed on 1 November 2026. The shipped JAR is byte-identical to the accepted file; the [artifact record](acceptance.json) identifies its checksum and scope.

Only Minecraft 26.3, NeoForge 26.3.0.99, Java 25 and the two Create Adapted files listed in the [parent guide](../README.md#english) are supported. Remove older versions of this companion before starting. Do not install it on the dedicated Minecraft server.

Initial placement, removed or derailed trains, and full position syncs beyond 64 blocks retain their recovery paths. Server permissions, outgoing packets and explicit teleport/vehicle packets are unchanged. This does not approve other Minecraft, NeoForge or Create versions.

Use the command above with matching cached libraries, JDK 25, Create and JetBrains annotations 26.0.2. The build downloads nothing. `verify.py` compares two independent builds and checks the compiled helpers, driver/observer cases and affected method bodies. Its 40 checks complement actual riding acceptance. Log output is limited to twelve reports.

Own code: [MIT](LICENSE), Copyright 2026 Roman Glos. See [NOTICE](NOTICE).

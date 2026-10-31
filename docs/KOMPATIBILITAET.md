# Minecraft, NeoForge und Java / Minecraft, NeoForge and Java

[Deutsch](#deutsch) · [English](#english)

## Deutsch

Der Manager verwaltet **eine Minecraft-Java-Instanz pro NAS**. Das Einrichtungsprojekt legt das dauerhafte Minecraft-Projekt an. Beide gehören zu derselben Installation. Andere Docker-Projekte werden nicht übernommen.

Manager, Minecraft, NeoForge und die mitgelieferten Zusatzdateien haben voneinander unabhängige Versionsnummern.

Diese Kombinationen werden mit passenden Visitor-Guard-Dateien ausgeliefert:

| Minecraft | NeoForge | Java | Visitor Guard |
| --- | --- | --- | --- |
| 26.3 | 26.3.0.99 | 25 | 1.0.5 |
| 1.21.1 | 21.1.265 | 21 | 1.0.5 |

Der Visitor Guard schützt den Server. Besucher sind standardmäßig Zuschauer ohne Operatorrechte; freigegebene Spieler können spielen. Spieler brauchen für diesen Schutz keine zusätzliche Guard-Datei auf ihrem Client. Andere Mods können passende Clientdateien erfordern. Erstelle das Clientpaket deshalb aus dem tatsächlich übernommenen Serverstand.

Die genannten Kombinationen wurden mit echten Clients geprüft. Der genaue Umfang und die Dateiidentitäten stehen in den [mitgelieferten Kompatibilitätsdaten](../artifacts/guard-acceptance-20261031.json). Die Ergebnisse gelten für diese Dateien und die dort aufgeführten Mods. Andere Versionen, zusätzliche Mods oder geänderte Gruppenrechte benötigen eine eigene Prüfung.

Der Manager bietet Kombinationen aus seinem Kompatibilitätskatalog an. Ein Versionswechsel prüft deine Mods in einer getrennten Umgebung, bevor du ihn übernimmst. Verwende für eine andere Minecraft-Version eine eigene Testwelt. Öffne eine neuere Welt niemals mit einer älteren Minecraft-Version.

**Fabric, Forge, Vanilla, Paper, Spigot, Quilt und Bedrock werden von den mitgelieferten Schutzdateien nicht unterstützt.** Ein vorhandener Quellordner oder ein Eintrag im offiziellen Versionskatalog bedeutet keine Unterstützung.

Für sitzende Create-Zugfahrten mit der passenden 26.3-Konfiguration gibt es eine [optionale Clientkorrektur](compatibility/create-trains/README.md). Sie gehört ausschließlich in das Clientpaket.

## English

The manager runs **one Minecraft Java instance per NAS**. The setup project creates the permanent Minecraft project; both belong to the same installation. Other Docker projects are not adopted.

Manager, Minecraft, NeoForge and the bundled companion files have independent version numbers.

The table above lists the supported combinations and their matching Visitor Guard files.

Visitor Guard protects the server. By default, visitors are spectators without operator rights; approved players can play. Players do not need an extra Guard file on their client. Other mods may require matching client files, so create the client pack from the server configuration that has actually been applied.

The listed combinations were checked with real clients. The [bundled compatibility data](../artifacts/guard-acceptance-20261031.json) records the exact scope, files and mod inventory. These results apply to those files. Other versions, additional mods or changed group permissions need their own checks.

The manager offers combinations from its compatibility catalogue. Before applying a version change, it checks your mods in a separate environment. Use a separate test world for another Minecraft version. Never open a newer world with an older Minecraft version.

**Fabric, Forge, Vanilla, Paper, Spigot, Quilt and Bedrock are not supported by the supplied protection files.** A source folder or an entry in an official version catalogue does not establish support.

An [optional client correction](compatibility/create-trains/README.md#english) is available for seated Create train journeys with the matching 26.3 configuration. It belongs only in the client pack.

## Dateien und Prüfsummen / Files and checksums

Die SHA-256-Prüfsumme identifiziert den genauen Inhalt einer Datei. Sie ersetzt keinen Funktionstest. Die mitgelieferten Manifeste halten Serverstart und Besucherschutztest getrennt fest. / A SHA-256 checksum identifies a file's exact contents. It does not replace functional testing. The supplied manifests record server-start and visitor-protection tests separately.

### Minecraft 26.3

- Datei / File: [mcj-guard-neoforge-1.0.5.jar](../artifacts/mcj-guard-neoforge-1.0.5.jar)
- Manifest: [guard.json](../artifacts/guard.json)
- SHA-256: `74686de28ea7f81ede7ef21af232396f4eb90b6285208769abd8680300e32f0c`

### Minecraft 1.21.1

- Datei / File: [mcj-guard-neoforge-1.21.1-1.0.5.jar](../artifacts/mcj-guard-neoforge-1.21.1-1.0.5.jar)
- Manifest: [guard-neoforge-1211.json](../artifacts/guard-neoforge-1211.json)
- SHA-256: `f75fca9813e1080e261b17a2b5d5c60d13fd15e4e223b2718350b1f992c86d8f`

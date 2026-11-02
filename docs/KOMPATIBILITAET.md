# Minecraft, NeoForge und Java / Minecraft, NeoForge and Java

[Deutsch](#deutsch) · [English](#english)

## Deutsch

Der Manager verwaltet **eine Minecraft-Java-Instanz pro NAS**. Das Einrichtungsprojekt legt das dauerhafte Minecraft-Projekt an. Beide gehören zu derselben Installation. Andere Docker-Projekte werden nicht übernommen.

Manager, Minecraft, NeoForge und die mitgelieferten Zusatzdateien haben voneinander unabhängige Versionsnummern.

Für diese bereits geprüften Kombinationen liegen aktualisierte Visitor-Guard-Dateien zur erneuten gezielten Schutzprüfung vor:

| Minecraft | NeoForge | Java | Visitor Guard |
| --- | --- | --- | --- |
| 26.3 | 26.3.0.99 | 25 | 1.0.7 |
| 1.21.1 | 21.1.265 | 21 | 1.0.7 |

Der Visitor Guard schützt den Server. Besucher sind standardmäßig Zuschauer ohne Operatorrechte; freigegebene Spieler können spielen. Spieler brauchen für diesen Schutz keine zusätzliche Guard-Datei auf ihrem Client. Andere Mods können passende Clientdateien erfordern. Erstelle das Clientpaket deshalb aus dem tatsächlich übernommenen Serverstand.

Die früheren Prüfungen mit echten Clients und Guard 1.0.5 bleiben in den [Kompatibilitätsdaten](../artifacts/guard-acceptance-20261031.json) erhalten. Die geänderten Schutzpfade von Guard 1.0.7 benötigen einen eigenen Nachweis; die alte Abnahme gilt nicht automatisch für neue Dateien. Den aktuellen Stand aller neun vorgesehenen Kombinationen mit Fabric, Forge und NeoForge zeigt die [Kompatibilitätsmatrix](KOMPATIBILITAET-MATRIX.md).

Der Manager bietet Kombinationen aus seinem Kompatibilitätskatalog an. Ein Versionswechsel prüft deine Mods in einer getrennten Umgebung, bevor du ihn übernimmst. Verwende für eine andere Minecraft-Version eine eigene Testwelt. Öffne eine neuere Welt niemals mit einer älteren Minecraft-Version.

**Fabric und Forge befinden sich in der Kompatibilitätsprüfung. Vanilla, Paper, Spigot, Quilt und Bedrock werden von den mitgelieferten Schutzdateien nicht unterstützt.** Ein vorhandener Quellordner oder ein Eintrag im offiziellen Versionskatalog bedeutet keine Unterstützung.

Für sitzende Create-Zugfahrten mit der passenden 26.3-Konfiguration gibt es eine [optionale Clientkorrektur](compatibility/create-trains/README.md). Sie gehört ausschließlich in das Clientpaket.

## English

The manager runs **one Minecraft Java instance per NAS**. The setup project creates the permanent Minecraft project; both belong to the same installation. Other Docker projects are not adopted.

Manager, Minecraft, NeoForge and the bundled companion files have independent version numbers.

The table above lists the previously tested combinations and their updated Visitor Guard files, which require targeted protection checks.

Visitor Guard protects the server. By default, visitors are spectators without operator rights; approved players can play. Players do not need an extra Guard file on their client. Other mods may require matching client files, so create the client pack from the server configuration that has actually been applied.

The earlier real-client results for Guard 1.0.5 remain in the [compatibility data](../artifacts/guard-acceptance-20261031.json). Guard 1.0.7 needs evidence for its changed protection paths; the earlier acceptance does not automatically apply to new files. The [compatibility matrix](KOMPATIBILITAET-MATRIX.md) records the current status of all nine planned Fabric, Forge and NeoForge combinations.

The manager offers combinations from its compatibility catalogue. Before applying a version change, it checks your mods in a separate environment. Use a separate test world for another Minecraft version. Never open a newer world with an older Minecraft version.

**Fabric and Forge are undergoing compatibility testing. Vanilla, Paper, Spigot, Quilt and Bedrock are not supported by the supplied protection files.** A source folder or an entry in an official version catalogue does not establish support.

An [optional client correction](compatibility/create-trains/README.md#english) is available for seated Create train journeys with the matching 26.3 configuration. It belongs only in the client pack.

## Dateien und Prüfsummen / Files and checksums

Die SHA-256-Prüfsumme identifiziert den genauen Inhalt einer Datei. Sie ersetzt keinen Funktionstest. Die mitgelieferten Manifeste halten Serverstart und Besucherschutztest getrennt fest. / A SHA-256 checksum identifies a file's exact contents. It does not replace functional testing. The supplied manifests record server-start and visitor-protection tests separately.

### Minecraft 26.3

- Datei / File: [mcj-guard-neoforge-1.0.7.jar](../artifacts/mcj-guard-neoforge-1.0.7.jar)
- Manifest: [guard.json](../artifacts/guard.json)
- SHA-256: `0a6b251a6d23f72cb6c82665d462ab36da4d8178201f58f19181ed83e079e868`

### Minecraft 1.21.1

- Datei / File: [mcj-guard-neoforge-1.21.1-1.0.7.jar](../artifacts/mcj-guard-neoforge-1.21.1-1.0.7.jar)
- Manifest: [guard-neoforge-1211.json](../artifacts/guard-neoforge-1211.json)
- SHA-256: `413bfa63c0bf42a297933c880fbe99d5c72483f2ee6a7652d0775765c549b03c`

# Minecraft, Modloader und Java / Minecraft, mod loaders and Java

[Deutsch](#deutsch) · [English](#english)

## Deutsch

Der Manager verwaltet **eine Minecraft-Java-Instanz pro NAS**. Das Einrichtungsprojekt legt das dauerhafte Minecraft-Projekt an. Beide gehören zu derselben Installation. Andere Docker-Projekte werden nicht übernommen.

Geprüft sind die folgenden Kombinationen mit dem jeweils passenden Visitor Guard. Minecraft-, Loader-, Java- und Mod-Versionen müssen zusammenpassen. Die Voreinstellung bleibt Minecraft **26.3**, NeoForge **26.3.0.99** und Java **25**.

| Minecraft | Modloader | Loader-Version / Loader version | Java | Visitor Guard |
|---|---|---|---|---|
| 1.20.1 | Fabric | 0.20.1 | 17 | 1.0.7 |
| 1.20.1 | Forge | 47.4.28 | 17 | 1.0.7 |
| 1.20.1 | NeoForge | 47.1.106 | 17 | 1.0.7 |
| 1.21.1 | Fabric | 0.20.1 | 21 | 1.0.7 |
| 1.21.1 | Forge | 52.1.20 | 21 | 1.0.7 |
| 1.21.1 | NeoForge | 21.1.265 | 21 | 1.0.7 |
| 26.3 | Fabric | 0.20.1 | 25 | 1.0.7 |
| 26.3 | Forge | 66.1.0 | 25 | 1.0.7 |
| 26.3 | NeoForge | 26.3.0.99 | 25 | 1.0.7 |

Für diese neun Kombinationen sind Installation, Serverstart, echte Clientverbindung, Besucherschutz, Rechtewechsel, Modverwaltung, Clientpakete und die zugeordneten Wartungsschritte belegt. Die [Abnahmematrix](KOMPATIBILITAET-MATRIX.md) nennt den genauen Umfang und die Dateiidentitäten. Die Prüfung gilt für den dort aufgeführten Modbestand; zusätzliche Mods benötigen ihre eigene Kompatibilitätsprüfung.

Der Visitor Guard gehört ausschließlich auf den Server. Besucher sind standardmäßig Zuschauer ohne Operatorrechte; freigegebene Spieler können spielen. Spieler benötigen keine Guard-Datei im Client. Andere Mods können passende Clientdateien erfordern. Erstelle das Clientpaket deshalb aus dem tatsächlich übernommenen Serverstand.

NeoForge **1.20.1** verwendet den historischen Loader **47.1.106**. Er ist nicht mit Forge **47.4.28** austauschbar. Wähle im Launcher dieselbe NeoForge-Version. Das exportierte Clientpaket übernimmt diese Zuordnung automatisch.

Ein Eintrag im offiziellen Versionskatalog erteilt keine Freigabe. **Vanilla, Paper, Spigot, Quilt und Bedrock werden von den mitgelieferten Schutzdateien nicht unterstützt.** Für andere Minecraft-/Loader-Versionen fehlt die Abnahme. Ein Versionswechsel prüft deine Mods in einer getrennten Umgebung, bevor du ihn übernimmst. Verwende für eine andere Minecraft-Version eine eigene Testwelt und öffne eine neuere Welt niemals mit einer älteren Minecraft-Version.

Für Create-Züge gibt es eine [optionale Clientkorrektur](compatibility/create-trains/README.md). Sie ist nur für die dort genannte NeoForge-26.3-/Create-Adapted-Konfiguration vorgesehen und gehört ausschließlich in den Client.

## English

The manager runs **one Minecraft Java instance per NAS**. The setup project creates the permanent Minecraft project; both belong to the same installation. Other Docker projects are not adopted.

The table above lists the tested combinations and their matching Visitor Guards. Minecraft, loader, Java and mod versions must match. The default remains Minecraft **26.3**, NeoForge **26.3.0.99** and Java **25**.

All nine combinations have evidence for installation, server startup, a real client connection, visitor protection, role changes, mod management, client packs and the associated maintenance steps. The [acceptance matrix](KOMPATIBILITAET-MATRIX.md) records the exact scope and file identities. Acceptance covers the listed mod inventory; additional mods need their own compatibility checks.

Visitor Guard belongs only on the server. Visitors are spectators without operator rights by default; approved players can play. Players do not need a Guard file on their client. Other mods may require matching client files, so create the client pack from the server configuration that has actually been applied.

NeoForge **1.20.1** uses the historical loader **47.1.106**, which is not interchangeable with Forge **47.4.28**. Select the same NeoForge version in your launcher. The exported client pack supplies this mapping automatically.

An official catalogue entry does not establish support. **Vanilla, Paper, Spigot, Quilt and Bedrock are not supported by the supplied protection files.** Other Minecraft/loader versions have not been accepted. A version switch checks your mods in a separate environment before applying them. Use a separate test world for another Minecraft version, and never open a newer world with an older Minecraft version.

An [optional Create train correction](compatibility/create-trains/README.md#english) is available only for the documented NeoForge 26.3/Create Adapted configuration. It belongs only in the client.

## Dateien und Prüfsummen / Files and checksums

Die SHA-256-Prüfsumme identifiziert den genauen Dateiinhalt. Sie ersetzt keinen Funktionstest. Alle neun Zuordnungen und Schutzdatei-Prüfsummen stehen in der [maschinenlesbaren Abnahmematrix](../artifacts/compatibility/release-matrix.json). Frühere Prüfungen bleiben mit ihren ursprünglichen Dateiidentitäten erhalten. / A SHA-256 hash identifies exact file contents; it does not replace functional testing. The machine-readable matrix records all nine mappings and guard hashes. Earlier results retain their original file identities.

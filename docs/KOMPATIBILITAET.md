# Minecraft, Modloader und Java / Minecraft, mod loaders and Java

[Deutsch](#deutsch) · [English](#english)

## Deutsch

Du kannst mit dem Manager **einen Minecraft-Java-Server pro NAS** verwalten. Das Einrichtungsprojekt legt dafür ein eigenes Minecraft-Projekt in UGOS an. Beide gehören zu derselben Installation; deine anderen Docker-Projekte bleiben unverändert.

Die folgende Tabelle zeigt die unterstützten Kombinationen. Fabric, Forge und NeoForge sind Modloader: Sie laden die Mods für deinen Minecraft-Server. Wähle einen davon und achte darauf, dass auch Minecraft, Java und deine Mods dazu passen. Der passende Besucherschutz (Visitor Guard) wird mitgeliefert. Voreingestellt sind Minecraft **26.3**, NeoForge **26.3.0.99** und Java **25**.

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

Für alle neun Kombinationen wurden die Installation, der Serverstart, die Verbindung mit einem echten Minecraft-Client, Besucherrechte, Rollenwechsel, Modverwaltung, Clientpakete und die zugehörigen Wartungsschritte geprüft. Welche Dateien und Mods dabei verwendet wurden, steht in der [Testübersicht](KOMPATIBILITAET-MATRIX.md). Diese Ergebnisse gelten nicht automatisch für jede zusätzliche Mod; neue Mods musst du gesondert auf Kompatibilität prüfen.

Der Visitor Guard gehört ausschließlich auf den Server. Besucher sind standardmäßig Zuschauer ohne Operatorrechte; freigegebene Spieler können spielen. Spieler benötigen keine Guard-Datei im Client. Andere Mods können passende Clientdateien erfordern. Erstelle das Clientpaket deshalb erst, nachdem du die gewünschten Änderungen auf dem Server übernommen hast.

NeoForge **1.20.1** verwendet den historischen Loader **47.1.106**. Er ist nicht mit Forge **47.4.28** austauschbar. Wähle im Launcher dieselbe NeoForge-Version. Das exportierte Clientpaket übernimmt diese Zuordnung automatisch.

Der offizielle Versionskatalog enthält auch Versionen, die der Manager noch nicht unterstützt. **Vanilla, Paper, Spigot, Quilt und Bedrock werden von den mitgelieferten Schutzdateien nicht unterstützt.** Unterstützt werden nur die Kombinationen aus der Tabelle oben. Ein Versionswechsel prüft deine Mods in einer getrennten Umgebung, bevor du ihn übernimmst. Verwende für eine andere Minecraft-Version eine eigene Testwelt und öffne eine neuere Welt niemals mit einer älteren Minecraft-Version.

Für Create-Züge gibt es eine [optionale Clientkorrektur](compatibility/create-trains/README.md). Sie ist nur für die dort genannte NeoForge-26.3-/Create-Adapted-Konfiguration vorgesehen und gehört ausschließlich in den Client.

## English

The manager runs **one Minecraft Java server per NAS**. Setup creates a separate Minecraft project in UGOS. Both projects belong to the same installation; your other Docker projects are left unchanged.

The table above lists the supported combinations. Fabric, Forge and NeoForge are mod loaders: they load the mods used by your server. Choose one and make sure your Minecraft, Java and mod versions match it. The matching protection mod, Visitor Guard, is included. The default is Minecraft **26.3**, NeoForge **26.3.0.99** and Java **25**.

All nine combinations have been checked for installation, startup, connection from a real Minecraft client, visitor protection, role changes, mod management, client packs and the relevant maintenance steps. The [test overview](KOMPATIBILITAET-MATRIX.md) records the files and mods used. These results do not automatically cover every additional mod; check new mods for compatibility separately.

Visitor Guard belongs only on the server. Visitors are spectators without operator rights by default; approved players can play. Players do not need a Guard file on their client. Other mods may require matching client files. Create the client pack after applying your changes to the server.

NeoForge **1.20.1** uses the historical loader **47.1.106**, which is not interchangeable with Forge **47.4.28**. Select the same NeoForge version in your launcher. The exported client pack supplies this mapping automatically.

The official version catalogue also lists versions that the manager does not yet support. **Vanilla, Paper, Spigot, Quilt and Bedrock are not supported by the supplied protection files.** Only the combinations in the table above are supported. A version switch checks your mods in a separate environment before applying them. Use a separate test world for another Minecraft version, and never open a newer world with an older Minecraft version.

An [optional Create train correction](compatibility/create-trains/README.md#english) is available only for the documented NeoForge 26.3/Create Adapted configuration. It belongs only in the client.

## Dateien und Prüfsummen / Files and checksums

Die SHA-256-Prüfsumme zeigt, ob zwei Dateien denselben Inhalt haben. Sie sagt allein nichts darüber aus, ob die Funktion geprüft wurde. Die genauen Versionen und Prüfsummen der neun Kombinationen stehen in der [Testmatrix als JSON-Datei](../artifacts/compatibility/release-matrix.json). Frühere Testergebnisse bleiben den damals verwendeten Dateien zugeordnet.

A SHA-256 checksum lets you check whether two files have identical contents. It does not, by itself, prove that a feature works. The [JSON test matrix](../artifacts/compatibility/release-matrix.json) lists exact versions and checksums for all nine combinations. Earlier results remain linked to the files used at the time.

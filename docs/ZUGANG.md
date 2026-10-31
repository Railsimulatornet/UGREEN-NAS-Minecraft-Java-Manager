# Zugang wiederherstellen

[Deutsch](#zugang-wiederherstellen) · [English](#english)

Für eine vorhandene Installation den Ersteinrichtungsassistenten nicht erneut
ausführen. Bestehende Welten und den Projektordner erhalten. Vor Änderungen ein
geprüftes Backup und die bisherige Compose-Datei sichern.

Ermittle bei einem vorhandenen UGOS-Projekt die wirkliche Identität:

```sh
PROJECT=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.project"}}')
COMPOSE=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')
SERVICE=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.service"}}')
test "$PROJECT" = ugreen_minecraft_java && test "$SERVICE" = manager || exit 1
docker compose -p "$PROJECT" -f "$COMPOSE" ps
```

Ein vorbereiteter, noch nicht bestätigter Adresswechsel verfällt nach zehn
Minuten automatisch. Danach die bisherige Adresse erneut öffnen. DNS und das
HTTPS-Zertifikat der alten Adresse müssen weiterhin eingerichtet sein.

Falls eine bereits aktivierte Adresse falsch konfiguriert ist, kann der
NAS-Administrator sie lokal mit dem mitgelieferten Werkzeug zurücksetzen.
Die folgenden Befehle gehören in ein **SSH-Terminal auf dem NAS**, nicht in die
Windows-Konsole. Voraussetzung sind ein laufender Container `mcj_manager`,
Python 3 auf dem NAS und Administratorrechte. Kopiere das Werkzeug aus dem
installierten Image in einen neuen temporären Ordner und führe diese Kopie aus:

```sh
MCJ_RECOVERY_DIR=$(mktemp -d) || exit 1
sudo docker cp mcj_manager:/opt/mcj/tools/recover_access.py "$MCJ_RECOVERY_DIR/recover_access.py" || exit 1
sudo python3 "$MCJ_RECOVERY_DIR/recover_access.py" --web-address https://minecraft.example.de
```

Eigene tatsächliche HTTPS-Adresse einsetzen. Das Werkzeug prüft die
Containerlabels, ändert ausschließlich die Webzugangskonfiguration und
verwirft einen ausstehenden Adresswechsel. Konten, Passwörter, MFA und Welten
bleiben unverändert. Der Minecraft-Server läuft weiter. Das Werkzeug lässt die
bisherige externe Freigabe bestehen. Nur für eine ausdrücklich beabsichtigte
Korrektur kann `--external-web local` beziehungsweise `--external-web allow`
angegeben werden. Die Anmeldung und MFA bleiben verpflichtend.

Der Manager akzeptiert Quelladressen eines Reverse-Proxys nur von den
einzelnen in `MCJ_TRUSTED_PROXIES` bestätigten IP-Adressen. Nach einer Änderung
der Proxy-IP diesen Wert in der bestehenden Compose-Datei korrigieren und
mit der oben ermittelten Identität nur den Manager neu erstellen:

```sh
docker compose -p "$PROJECT" -f "$COMPOSE" up -d --no-deps --no-build --pull never "$SERVICE"
```

Keine pauschale Freigabe für alle Proxyadressen und keine Weiterleitung von
Controller- oder RCON-Ports ins Internet einrichten. Konkrete private
Heimnetze für einen direkten Zugang können in `MCJ_LOCAL_NETWORKS` angegeben
werden. Der HTTPS-Proxy muss Host und echte Quelladresse korrekt weitergeben.

## English

### Recover access to an existing installation

Do not run first-time setup again over an existing installation. Keep the world
and project folders. Before making changes, retain a verified backup and the
current Compose configuration. This section is for NAS administrators; normal
first-time setup is described in the [installation guide](INSTALLATION-EN.md).

Read the existing project's identity from its container labels:

```sh
PROJECT=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.project"}}')
COMPOSE=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')
SERVICE=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.service"}}')
test "$PROJECT" = ugreen_minecraft_java && test "$SERVICE" = manager || exit 1
docker compose -p "$PROJECT" -f "$COMPOSE" ps
```

An address change that has not been confirmed expires after ten minutes. Reopen
the previous address afterwards. Its DNS and HTTPS certificate must still be
configured.

If an incorrect address has already been activated, the NAS administrator can
correct it locally with the supplied tool.
Run the following commands in an **SSH terminal on the NAS**, not in the
Windows console. You need a running `mcj_manager` container, Python 3 on the NAS
and administrator privileges. Copy the tool from the installed image into a new
temporary directory and run that copy:

```sh
MCJ_RECOVERY_DIR=$(mktemp -d) || exit 1
sudo docker cp mcj_manager:/opt/mcj/tools/recover_access.py "$MCJ_RECOVERY_DIR/recover_access.py" || exit 1
sudo python3 "$MCJ_RECOVERY_DIR/recover_access.py" --web-address https://minecraft.example.de
```

Replace the example with your actual HTTPS address. The tool checks container
labels, changes only web access settings and cancels a pending address change.
Accounts, passwords, two-factor settings and worlds remain unchanged.
The Minecraft server keeps running. The existing external-access setting is retained. Only when you
intend to change that setting, add `--external-web local` or
`--external-web allow`. Your password and security code remain required.

The manager accepts forwarded client addresses only from the individual proxy
IP addresses approved in `MCJ_TRUSTED_PROXIES`. If the proxy IP changes, correct
that value in the existing Compose file and recreate only the manager using the
identity read above:

```sh
docker compose -p "$PROJECT" -f "$COMPOSE" up -d --no-deps --no-build --pull never "$SERVICE"
```

Do not trust all proxy addresses or expose the controller or RCON ports to the
internet. Set the specific private networks for direct home access in
`MCJ_LOCAL_NETWORKS`. Your HTTPS proxy must forward the host and real client
address correctly.

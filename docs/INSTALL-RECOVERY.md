# Administration und Wiederherstellung / Administration and recovery

Diese Seite ist für NAS-Administratoren. Für eine normale Erstinstallation verwende [README](../README.md#deutsch), für Updates [AKTUALISIEREN.md](AKTUALISIEREN.md).

This page is for NAS administrators. For normal first-time setup, use [README](../README.md#english); for updates, use [AKTUALISIEREN.md](AKTUALISIEREN.md#english).

## Daten erhalten / Preserve data

Der gewählte Minecraft-Datenordner enthält `manager`, `mcj_controller` und `mcj_minecraft`. Manager-Datenbank und `manager/secrets` gehören zusammen: Ein neuer Verschlüsselungsschlüssel kann alte Geheimnisse nicht entschlüsseln. Backups liegen im separat gewählten Backupordner.

Your chosen Minecraft data directory contains `manager`, `mcj_controller` and `mcj_minecraft`. Restore the manager database together with `manager/secrets`: a new encryption key cannot decrypt old settings. Game backups are stored in the separately selected backup directory.

Kopiere eine laufende SQLite-Datenbank nicht ohne ihre aktiven WAL-Daten. Nutze ein konsistentes SQLite-Backup oder stoppe die App kontrolliert. Vor einer Wiederherstellung zuerst den aktuellen Stand sichern. Private Schlüssel, SMTP-Passwörter, Webhooks und Benutzerdaten gehören nicht in öffentliche Supportmeldungen.

Do not copy a running SQLite database without its active WAL data. Use a consistent SQLite backup or stop the app cleanly. Save the current state before restoring. Never post private keys, SMTP passwords, webhooks or user data in public support requests.

## Tatsächliche Compose-Identität / Actual Compose identity

Vor jedem manuellen Compose-Build oder Deploy Projekt und Service aus den laufenden Container-Labels ermitteln. Den Namen niemals aus einem Ordner ableiten.

Before a manual Compose build or deployment, derive the project and service from actual container labels. Never infer the project name from a directory.

```sh
PROJECT=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.project"}}')
COMPOSE=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')
SERVICE=$(docker inspect mcj_manager --format '{{index .Config.Labels "com.docker.compose.service"}}')
docker compose -p "$PROJECT" -f "$COMPOSE" ps
```

Prüfe die ermittelten Werte und sichere die vorhandene Konfiguration, bevor du Änderungen ausführst. Für gewöhnliche Updates verwende den dokumentierten UGOS-Weg. Ein Image-Tag allein beweist nicht, welche Version läuft; prüfe bei der Diagnose zusätzlich Image-ID und Revisionslabel.

Verify those values and back up the configuration before making changes. Use the documented UGOS workflow for normal updates. An image tag alone does not prove the running version; diagnostics should also check the image ID and revision label.

## Zugriff / Access

Ein noch nicht bestätigter Adresswechsel verfällt nach zehn Minuten. Die bisherige Adresse bleibt bis zur Bestätigung gültig. Bei einer falschen bereits aktivierten Adresse siehe [ZUGANG.md](ZUGANG.md). Anmeldung und 2FA bleiben bei der Wiederherstellung verpflichtend.

An unconfirmed address change expires after ten minutes. The previous address remains valid until confirmation. For an incorrectly activated address, see [access recovery](ZUGANG.md#english). Your password and security code remain required during recovery.

## Rückfall nach einem Update / Update rollback

Der UGOS-Updater speichert einen privaten Rückfallstand unter `mcj_controller/.rollback/ugos-app-…`. Er enthält Datenbank, Compose-Konfiguration und Laufzeit-Auswahl. Schlüsseldateien werden nicht ersetzt. Ein automatischer Rückfall wird ausdrücklich als solcher gemeldet. Prüfe anschließend den Dienstzustand und die Ereignisse.

The UGOS updater saves a private rollback copy under `mcj_controller/.rollback/ugos-app-…`, including the database, Compose configuration and runtime selection. Key files are not replaced. Automatic rollback is reported explicitly. Check service health and events afterwards.

Importiere den Minecraft-Datenordner niemals nachträglich als neuen UGOS-Projekt-Speicherpfad und repariere Dateirechte nicht pauschal rekursiv. Sichere vorhandene Rückfallstände, bis die Wiederherstellung geprüft ist.

Never import the Minecraft data directory as a new UGOS project storage path or apply broad recursive permission changes. Keep existing rollback copies until recovery has been verified.

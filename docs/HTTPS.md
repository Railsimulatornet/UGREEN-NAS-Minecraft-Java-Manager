# HTTPS im Heimnetz / Local HTTPS

## Deutsch

Der Installer erstellt ein Zertifikat für deine NAS-Adresse. Damit der Browser dieser lokalen Installation vertraut:

1. Öffne **UGOS → Dateien → dein Docker-Ordner → mcj-einrichtung**.
2. Lade nur **Heimnetz-Zertifikat.crt** herunter. Das ist das öffentliche Vertrauenszertifikat; private Schlüssel bleiben auf dem NAS.
3. Vergleiche den SHA-256-Fingerabdruck mit **ZERTIFIKAT-HINWEIS.txt** im selben NAS-Ordner.
4. Windows: Zertifikat öffnen → **Zertifikat installieren → Aktueller Benutzer → Alle Zertifikate in folgendem Speicher speichern → Vertrauenswürdige Stammzertifizierungsstellen**. Importiere ausschließlich das Zertifikat deiner Installation.
5. Firefox kann einen eigenen Speicher verwenden: **Einstellungen → Datenschutz & Sicherheit → Zertifikate anzeigen → Zertifizierungsstellen → Importieren**. Auf dem Smartphone verwendest du die Zertifikatverwaltung des Betriebssystems bzw. Browsers.
6. Öffne die NAS-Adresse erneut. Schalte die Browser-Zertifikatsprüfung nicht allgemein aus.

Später findest du Ablaufdatum und Erneuerung unter **Einstellungen → Infrastruktur und Freigabe**. Die normale Erneuerung erhält das vorhandene Vertrauen.

### SHA-256-Fingerabdruck unter Windows vergleichen

Lade das öffentliche Zertifikat über deine vertraute UGOS-Anmeldung herunter. Öffne daneben **ZERTIFIKAT-HINWEIS.txt** im UGOS-Dateimanager. Vergleiche die dort als SHA-256 angegebenen Zeichen mit dem heruntergeladenen Zertifikat, bevor du ihm vertraust.

Für eine genaue Prüfung ohne Zusatzprogramm:

1. Suche im Windows-Startmenü nach **Windows PowerShell** und öffne es normal; Administratorrechte sind nicht nötig.
2. Kopiere den folgenden Block hinein. Er liest ausschließlich eine lokale Zertifikatdatei und ändert keinen Zertifikatspeicher.
3. Wenn nach der Datei gefragt wird, füge den vollständigen Pfad deiner heruntergeladenen **Heimnetz-Zertifikat.crt** ein. Im Explorer erhältst du ihn über **Als Pfad kopieren**. Drücke die Eingabetaste.

```powershell
$mcjCertPath = (Read-Host 'Pfad / path: Heimnetz-Zertifikat.crt').Trim('"')
$mcjCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($mcjCertPath)
$mcjSha = [System.Security.Cryptography.SHA256]::Create()
[BitConverter]::ToString($mcjSha.ComputeHash($mcjCert.RawData)).Replace('-', '')
$mcjSha.Dispose()
$mcjCert.Reset()
```

Das Ergebnis hat **64 Zeichen**. Groß-/Kleinschreibung, Doppelpunkte und Leerzeichen sind beim Vergleich unerheblich; alle übrigen Zeichen müssen übereinstimmen. Bei einer Abweichung nicht importieren: NAS-Adresse und Datei prüfen und das Zertifikat erneut über UGOS herunterladen.

Die Windows-Anzeige **Fingerabdruck** kann SHA-1 mit 40 Zeichen meinen. Sie ist nicht der hier benötigte SHA-256-Wert. Auch die Prüfsumme der Textdatei ist nicht der Zertifikatsfingerabdruck: Der obige Block berechnet ihn aus dem eingelesenen Zertifikat. [Microsoft erklärt den Unterschied der Fingerabdruckverfahren.](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.x509certificates.x509certificate2.thumbprint)

## English

The installer creates a certificate for your NAS address. To trust this local installation:

1. Open **UGOS → Files → your Docker directory → mcj-einrichtung**.
2. Download only **Heimnetz-Zertifikat.crt**. This is the public trust certificate; private keys stay on the NAS.
3. Compare its SHA-256 fingerprint with **ZERTIFIKAT-HINWEIS.txt** in the same NAS directory.
4. Windows: open the certificate → **Install Certificate → Current User → Place all certificates in the following store → Trusted Root Certification Authorities**. Import only your installation's certificate.
5. Firefox may use its own store: **Settings → Privacy & Security → View Certificates → Authorities → Import**. On a phone, use the operating system's or browser's certificate management.
6. Open the NAS address again. Do not disable browser certificate checks globally.

Later, check the expiry date and renew under **Settings → Infrastructure and access**. Normal renewal preserves existing trust.

### Compare the SHA-256 fingerprint on Windows

Download the public certificate through your trusted UGOS login. Open **ZERTIFIKAT-HINWEIS.txt** alongside it in UGOS Files. Before trusting the certificate, compare the SHA-256 value in that note with the downloaded certificate.

For an exact check without extra software:

1. Find **Windows PowerShell** in the Start menu and open it normally. Administrator privileges are not required.
2. Paste the block below. It only reads a local certificate file; it does not change any certificate store.
3. At the prompt, paste the full path of the downloaded **Heimnetz-Zertifikat.crt**. Use **Copy as path** in File Explorer to obtain it, then press Enter.

```powershell
$mcjCertPath = (Read-Host 'Pfad / path: Heimnetz-Zertifikat.crt').Trim('"')
$mcjCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($mcjCertPath)
$mcjSha = [System.Security.Cryptography.SHA256]::Create()
[BitConverter]::ToString($mcjSha.ComputeHash($mcjCert.RawData)).Replace('-', '')
$mcjSha.Dispose()
$mcjCert.Reset()
```

The result has **64 characters**. Ignore letter case, colons and spaces when comparing; all other characters must match. If they differ, do not import the certificate. Check the NAS address and file, then download the certificate again through UGOS.

Windows may display a 40-character SHA-1 value as **Thumbprint**. That is different from the SHA-256 value required here. A text-file checksum is also different from a certificate fingerprint: the block above calculates the fingerprint from the parsed certificate. [Microsoft explains certificate thumbprint algorithms.](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.x509certificates.x509certificate2.thumbprint)

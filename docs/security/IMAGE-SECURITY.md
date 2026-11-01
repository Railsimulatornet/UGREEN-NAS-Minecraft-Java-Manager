# Image-Prüfung / Image security

## Deutsch

Das Manager-Image ist nicht schwachstellenfrei. Der bewertete Paketstand vom 31.10.2026 enthält **44 HIGH-Paketzeilen zu acht CVEs**; der damalige Scannerbericht nennt dafür keine verfügbare Paketkorrektur. Mehrere Zeilen können dieselbe Ursache betreffen. Die [Paketzuordnung](image-baseline-1.0.0.json) bleibt vollständig erhalten und unterdrückt keine Scannerergebnisse.

| Befund | Bewertung der ausgelieferten Aufrufe |
| --- | --- |
| CVE-2026-76642, CVE-2026-78409, CVE-2026-78410 | Die betroffenen libmount-/X-mount-Aufrufe werden von MCJ nicht verwendet. Docker-Bind-Mounts verarbeitet der externe Docker-Dienst. Die Image-Pakete bleiben betroffen. |
| CVE-2026-78408 | Kein MCJ-Aufrufer verwendet `nsenter --join-cgroup`. Das ist kein Paketfix. |
| CVE-2026-54369 | Kein ausgelieferter MCJ-Pfad ruft die betroffenen libacl-Pfadfunktionen oder ACL-Wiederherstellung über GNU tar auf. |
| CVE-2025-69720 | `infocmp` ist enthalten, wird aber von Manager, Steuerungsdienst und Einrichtungs-/Updatehelfern nicht ausgeführt. |
| CVE-2026-16742 | Die bezeichnete Komponente `systemd-homed` ist im Image nicht enthalten. Vorhandene libsystemd-/libudev-Pakete allein belegen diesen Aufruf nicht. |
| CVE-2026-9538 | Das bezeichnete Perl-Modul `Archive::Tar` ist nicht enthalten. MCJ verwendet Python für seine Archive. |

Diese Bewertung gilt für die ausgelieferten Aufrufe und Paketversionen. Neue Aufrufer, andere Bereitstellungen, neue Erkenntnisse und verfügbare Paketkorrekturen erfordern eine erneute Bewertung. Sie sagt nichts über die Pakete des NAS-Betriebssystems aus. Der Steuerungsdienst hat über den Docker-Socket erhebliche Hostrechte; ein unprivilegierter Containerbenutzer ersetzt an dieser Grenze keine Abschottung.

Der Workflow **Veröffentlichtes Image prüfen** untersucht wöchentlich dienstags den festen Registry-Digest aus der Repository-Variable `MCJ_RELEASE_IMAGE_DIGEST`. Er sichert den vollständigen Bericht und den Vergleich 90 Tage als Actions-Artefakte. Neue hohe/kritische Befunde, eine Hochstufung auf kritisch oder eine neu verfügbare/geänderte Paketkorrektur lassen den Lauf fehlschlagen und eröffnen beziehungsweise aktualisieren ein zugehöriges Issue. Scannerfehler erscheinen als fehlgeschlagener Lauf. Es werden keine Images ausgetauscht, Vorschläge zusammengeführt oder NAS-Dienste verändert.

Nach einer späteren Veröffentlichung muss der Verantwortliche die Variable bewusst auf deren freigegebenen Digest setzen und den ersten Lauf kontrollieren. Eine Konfiguration allein ist kein erfolgreicher Prüflauf. Alte Berichte sind zeitbezogene Nachweise.

Primärquellen zu den Paketmeldungen: [Debian util-linux](https://security-tracker.debian.org/tracker/source-package/util-linux), [ACL](https://security-tracker.debian.org/tracker/CVE-2026-54369), [ncurses](https://security-tracker.debian.org/tracker/CVE-2025-69720), [systemd](https://security-tracker.debian.org/tracker/CVE-2026-16742), [Perl](https://security-tracker.debian.org/tracker/CVE-2026-9538).

## English

The manager image is not vulnerability-free. The package baseline reviewed on 31 October 2026 contains **44 HIGH package findings covering eight CVEs**, with no available package fix listed in that scan. Multiple rows can describe one cause. The complete [package mapping](image-baseline-1.0.0.json) is retained; it suppresses no scan results.

The shipped MCJ paths do not invoke the affected libmount/X-mount functions, `nsenter --join-cgroup`, libacl pathname functions, GNU tar ACL restoration or `infocmp`. The packages remain present and are not claimed to be fixed. The specifically reported `systemd-homed` component and Perl `Archive::Tar` module are absent. This assessment applies to the shipped calls and package versions, not to the NAS operating system. New callers, deployments, findings or available fixes require reassessment. The controller's Docker socket provides substantial host authority; a non-root container user does not isolate that boundary.

The **Veröffentlichtes Image prüfen** workflow scans the fixed registry digest in `MCJ_RELEASE_IMAGE_DIGEST` every Tuesday. It retains the full report and comparison as Actions artifacts for 90 days. New high/critical findings, escalation to critical or a newly available/changed package fix fail the run and create or update a related issue. Scanner failures appear as failed runs. It never replaces images, merges proposals or changes NAS services.

For a later release, the maintainer must deliberately update the variable to the approved digest and check the first run. A configured workflow is not a successful scan. Reports describe their recorded point in time. The Debian links above are the primary package references.

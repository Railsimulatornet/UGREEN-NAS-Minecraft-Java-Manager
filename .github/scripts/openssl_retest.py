"""Select the version published by Debian that fixes every tracked OpenSSL issue."""

import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

CVES = ("CVE-2026-107494", "CVE-2026-124709")
TRACKER = "https://security-tracker.debian.org/tracker/data/json"
SUITES = ("trixie", "trixie-security")
VERSION = re.compile(r"[0-9][0-9A-Za-z.+:~\-]{0,79}")
COMPRESSED_LIMIT = 32 * 1024 * 1024
UNCOMPRESSED_LIMIT = 128 * 1024 * 1024


def at_least(version, minimum):
    return subprocess.run(
        ["dpkg", "--compare-versions", version, "ge", minimum], check=False
    ).returncode == 0


def fixed_candidate(data, compare=at_least):
    releases = [data["openssl"][cve]["releases"]["trixie"] for cve in CVES]
    requirements = [row.get("fixed_version", "") for row in releases]
    if any(row["status"] != "resolved" for row in releases):
        return None
    if any(not VERSION.fullmatch(value) or value == "0" for value in requirements):
        return None

    candidate = None
    for suite in SUITES:
        published = [row["repositories"].get(suite, "") for row in releases]
        version = published[0]
        if not version or any(value != version for value in published):
            continue
        if not VERSION.fullmatch(version) or not all(compare(version, fix) for fix in requirements):
            continue
        if candidate is None or compare(version, candidate):
            candidate = version
    return candidate


def tracker_data():
    request = urllib.request.Request(TRACKER, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.headers.get("Content-Encoding") == "gzip":
            with gzip.GzipFile(fileobj=response) as stream:
                content = stream.read(UNCOMPRESSED_LIMIT + 1)
        else:
            content = response.read(COMPRESSED_LIMIT + 1)
            if len(content) > COMPRESSED_LIMIT:
                raise ValueError("Debian-Tracker-Daten überschreiten das Größenlimit")
    if len(content) > UNCOMPRESSED_LIMIT:
        raise ValueError("Debian-Tracker-Daten überschreiten das Größenlimit")
    return json.loads(content)


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True, timeout=35)


def main():
    revision = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Ungültiger GitHub-Quellstand")

    version = fixed_candidate(tracker_data())
    if version is None:
        message = "Debian hat für Trixie noch kein verfügbares Paket mit beiden OpenSSL-Korrekturen gemeldet."
    else:
        title = f"OpenSSL {version} @ {revision}"
        history = json.loads(gh(
            "run", "list", "--workflow", "image.yml", "--commit", revision,
            "--event", "workflow_dispatch", "--limit", "30",
            "--json", "displayTitle,status,conclusion",
        ))
        already_requested = any(
            run["displayTitle"] == title
            and (run["status"] != "completed" or run["conclusion"] == "success")
            for run in history
        )
        if already_requested:
            message = f"OpenSSL {version} wird für diesen Quellstand bereits geprüft oder hat bestanden."
        else:
            gh(
                "workflow", "run", "image.yml", "--ref", "main",
                "-f", f"expected_revision={revision}", "-f", f"openssl_minimum={version}",
                "-f", "build_image=true", "-f", "full_validation=true",
                "-f", "publish_image=false", "-f", "installation_tags=false",
                "-f", "anonymous_installation=false",
            )
            message = f"Für OpenSSL {version} wurde ein vollständiger Image-Test angefordert."
    print(message)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(message + "\n")


if __name__ == "__main__":
    main()

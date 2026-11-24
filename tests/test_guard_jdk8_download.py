"""Exercise the JDK bootstrap with fake downloads and extraction, without a JDK.

Only the copied test script's digest is replaced with the real SHA256 of a tiny
fixture. Verification uses the real sha256sum; the production pin is unchanged.
"""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".github/scripts/prepare_guard_jdk8.sh"


class GuardJdkDownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="guard-jdk-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runner = self.root / "runner"
        self.runner.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "verified-fixture.tar.gz"
        self.fixture.write_bytes(b"synthetic archive for isolated integrity tests\n")
        source, count = re.subn(
            r"(?m)^expected_sha256='[0-9a-f]{64}'$",
            f"expected_sha256='{hashlib.sha256(self.fixture.read_bytes()).hexdigest()}'",
            SOURCE.read_text())
        self.assertEqual(count, 1, "Exactly one fixed archive digest is required")
        self.script = self.root / "prepare.sh"
        self.script.write_text(source)
        self.events = self.root / "events"
        self.downloads = self.root / "downloads"
        self.destination = self.root / "jdk"
        self.make_command("curl", r'''#!/bin/bash
set -euo pipefail
output=''
while (($#)); do
  if [[ "$1" == --output ]]; then output="$2"; shift 2; else shift; fi
done
[[ -n "$output" ]] || exit 91
count=0
if [[ -f "$TEST_DOWNLOADS" ]]; then
  while IFS= read -r previous; do
    [[ ! -e "$previous" ]] || { printf 'Previous bad download remains\n' >&2; exit 92; }
    count=$((count + 1))
  done < "$TEST_DOWNLOADS"
fi
printf '%s\n' "$output" >> "$TEST_DOWNLOADS"
read -r -a responses <<< "$TEST_RESPONSES"
response="${responses[$count]:-unexpected}"
printf 'curl:%s\n' "$response" >> "$TEST_EVENTS"
case "$response" in
  good) cp -- "$TEST_FIXTURE" "$output" ;;
  bad) printf 'corrupted archive\n' > "$output" ;;
  empty) : > "$output" ;;
  missing) rm -f -- "$output" ;;
  http) printf 'error response\n' > "$output"; printf 'curl: HTTP failure\n' >&2; exit 22 ;;
  *) printf 'Unexpected extra download\n' >&2; exit 93 ;;
esac
''')
        self.make_command("tar", r'''#!/bin/bash
set -euo pipefail
archive=''
destination=''
while (($#)); do
  case "$1" in
    --file) archive="$2"; shift 2 ;;
    --directory) destination="$2"; shift 2 ;;
    *) shift ;;
  esac
done
printf 'tar\n' >> "$TEST_EVENTS"
cmp -- "$archive" "$TEST_FIXTURE" || exit 94
[[ "$TEST_TAR_FAIL" == 0 ]] || exit 2
mkdir -p -- "$destination/bin"
for name in java javac; do
  printf '#!/bin/bash\nprintf "%s\\n" >> "$TEST_EVENTS"\n' "$name" > "$destination/bin/$name"
  chmod +x "$destination/bin/$name"
done
''')
        self.make_command("sleep", "#!/bin/bash\nexit 0\n")

    def make_command(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def run_script(self, responses=(), *, candidate=None, tar_fails=False):
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin", "LC_ALL": "C",
            "RUNNER_TEMP": str(self.runner), "TEST_FIXTURE": str(self.fixture),
            "TEST_EVENTS": str(self.events), "TEST_DOWNLOADS": str(self.downloads),
            "TEST_RESPONSES": " ".join(responses), "TEST_TAR_FAIL": str(int(tar_fails)),
        }
        args = ["bash", str(self.script), str(self.destination)]
        if candidate is not None:
            args.append(str(candidate))
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
        events = self.events.read_text().splitlines() if self.events.exists() else []
        downloads = self.downloads.read_text().splitlines() if self.downloads.exists() else []
        self.assertEqual(len(downloads), len(set(downloads)), "Every retry needs a fresh temporary file")
        self.assertEqual(list(self.runner.iterdir()), [], "Download files must be cleaned up")
        return result, events, downloads

    def test_first_valid_download_is_verified_and_used_once(self):
        result, events, downloads = self.run_script(["good"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["curl:good", "tar", "java", "javac"])
        self.assertEqual(len(downloads), 1)

    def test_bad_then_good_download_recovers_without_executing_bad_bytes(self):
        result, events, downloads = self.run_script(["bad", "good"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["curl:bad", "curl:good", "tar", "java", "javac"])
        self.assertEqual(len(downloads), 2)

    def test_last_allowed_download_can_recover(self):
        result, events, downloads = self.run_script(["bad", "missing", "good"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["curl:bad", "curl:missing", "curl:good", "tar", "java", "javac"])
        self.assertEqual(len(downloads), 3)

    def test_corrupt_empty_missing_or_http_failures_stop_after_three_downloads(self):
        for response in ("bad", "empty", "missing", "http"):
            with self.subTest(response=response):
                for path in (self.events, self.downloads):
                    path.unlink(missing_ok=True)
                result, events, downloads = self.run_script([response] * 3)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(events, [f"curl:{response}"] * 3)
                self.assertEqual(len(downloads), 3)
                self.assertFalse(self.destination.exists())
                self.assertIn("ERROR:", result.stderr)

    def test_http_failure_can_recover_within_the_same_download_limit(self):
        result, events, downloads = self.run_script(["http", "good"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["curl:http", "curl:good", "tar", "java", "javac"])
        self.assertEqual(len(downloads), 2)

    def test_supplied_valid_candidate_is_kept_without_downloading(self):
        result, events, downloads = self.run_script(candidate=self.fixture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["tar", "java", "javac"])
        self.assertEqual(downloads, [])
        self.assertTrue(self.fixture.exists())

    def test_supplied_bad_or_missing_candidate_is_rejected_without_downloading(self):
        for exists in (True, False):
            with self.subTest(exists=exists):
                candidate = self.root / "candidate.tar.gz"
                if exists:
                    candidate.write_bytes(b"corrupted candidate")
                else:
                    candidate.unlink()
                result, events, downloads = self.run_script(candidate=candidate)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(events, [])
                self.assertEqual(downloads, [])
                self.assertEqual(candidate.exists(), exists)
                self.assertFalse(self.destination.exists())

    def test_existing_destination_is_not_overwritten(self):
        self.destination.mkdir()
        marker = self.destination / "keep"
        marker.write_text("existing installation")
        result, events, downloads = self.run_script(["good"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ["curl:good"])
        self.assertEqual(marker.read_text(), "existing installation")
        self.assertEqual(len(downloads), 1)

    def test_failed_extraction_never_executes_tools(self):
        result, events, downloads = self.run_script(["good"], tar_fails=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ["curl:good", "tar"])
        self.assertEqual(len(downloads), 1)


if __name__ == "__main__":
    unittest.main()

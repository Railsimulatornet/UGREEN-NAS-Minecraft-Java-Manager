import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "openssl_retest", Path(__file__).parents[1] / ".github/scripts/openssl_retest.py"
)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def tracker(*releases):
    return {"openssl": {
        cve: {"releases": {"trixie": item}}
        for cve, item in zip(watch.CVES, releases)
    }}


def row(fix, archive, status="resolved"):
    return {
        "status": status,
        "fixed_version": fix,
        "repositories": {"trixie": "1+deb13u1", "trixie-security": archive},
    }


def compare(version, minimum):
    return int(version.rsplit("u", 1)[1]) >= int(minimum.rsplit("u", 1)[1])


class OpenSslRetestTests(unittest.TestCase):
    def test_both_fixes_must_be_available_in_the_same_stable_repository(self):
        first = row("1+deb13u2", "1+deb13u3")
        second = row("1+deb13u3", "1+deb13u3")
        self.assertEqual(watch.fixed_candidate(tracker(first, second), compare), "1+deb13u3")
        for incomplete in [
            row("1+deb13u3", "1+deb13u2"),
            {**second, "status": "open"},
            row("1+deb13u4", "1+deb13u3"),
            row("0", "1+deb13u3"),
        ]:
            self.assertIsNone(watch.fixed_candidate(tracker(first, incomplete), compare))

    def test_only_unverified_candidates_are_dispatched(self):
        revision = "a" * 40
        version = "1+deb13u3"
        for status, conclusion, dispatch in [
            ("in_progress", None, False),
            ("completed", "success", False),
            ("completed", "failure", True),
        ]:
            with self.subTest(status=status, conclusion=conclusion):
                history = json.dumps([{
                    "displayTitle": f"OpenSSL {version} @ {revision}",
                    "status": status,
                    "conclusion": conclusion,
                }])
                with (
                    patch.dict(watch.os.environ, {"GITHUB_SHA": revision, "GITHUB_STEP_SUMMARY": "summary"}),
                    patch.object(watch, "tracker_data"),
                    patch.object(watch, "fixed_candidate", return_value=version),
                    patch.object(watch, "gh", return_value=history) as github,
                    patch.object(watch.Path, "open", return_value=io.StringIO()),
                ):
                    watch.main()
                self.assertEqual(github.call_count, 2 if dispatch else 1)
                if dispatch:
                    args = github.call_args.args
                    self.assertTrue({
                        "publish_image=false", "installation_tags=false", "build_image=true",
                        "full_validation=true", f"expected_revision={revision}", f"openssl_minimum={version}",
                    } <= set(args))


if __name__ == "__main__":
    unittest.main()

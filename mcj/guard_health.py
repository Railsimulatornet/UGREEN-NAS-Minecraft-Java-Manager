"""Validate the reporting protocol and the identity of the selected guard build."""
import math
import time

PROTOCOL = 1
# Only this previously shipped artifact used the protocol marker as its build version.
# Retained for its controlled upgrade/rollback; never applies to a new or unknown JAR.
LEGACY_REPORTERS = {'a8edc2bfae97a5ec79c0f3ddefa3f936aad6afb4f319d1ea8b05f6f6dac79156': '1.0.4'}

def verified(report, artifact, now=None):
    now=time.time() if now is None else now
    at=report.get('at')
    if type(at) not in (int,float) or not math.isfinite(at) or not -2 <= now-at < 15:return False
    if report.get('online_mode') is not True:return False
    if report.get('guard_protocol') == PROTOCOL and type(report.get('guard_protocol')) is int:
        return bool(artifact.get('version') and report.get('guard_version') == artifact['version'])
    return (report.get('guard_protocol') is None and report.get('guard_version') == '1.0.0'
            and LEGACY_REPORTERS.get(artifact.get('sha256')) == artifact.get('version') and artifact.get('version') is not None)

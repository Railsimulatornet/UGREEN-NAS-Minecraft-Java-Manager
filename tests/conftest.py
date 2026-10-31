"""Create disposable credentials with the same private default as the NAS installer."""
import os

def pytest_sessionstart(session):
    # Production rejects world-readable keys. Do not weaken that check for Linux CI.
    # Tests for deliberately unsafe permissions still set their own explicit modes.
    session.config._mcj_previous_umask=os.umask(0o077)

def pytest_sessionfinish(session,exitstatus):
    os.umask(session.config._mcj_previous_umask)

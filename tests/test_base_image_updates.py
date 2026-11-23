import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
MINIMUM = {
    'apt': '3.0.4',
    'libapt-pkg7.0': '3.0.4',
    'zlib1g': '1:1.3.dfsg+really1.3.1-1+deb13u1',
}
OLDER = {
    'apt': '3.0.3',
    'libapt-pkg7.0': '3.0.3',
    'zlib1g': '1:1.3.dfsg+really1.3.1-1',
}
NEWER = {
    'apt': '3.0.10',
    'libapt-pkg7.0': '3.0.10',
    'zlib1g': '1:1.3.dfsg+really1.3.1-1+deb13u2',
}


def run_package_step(tmp_path, versions, fail_command=''):
    dockerfile = (ROOT / 'Dockerfile').read_text()
    block = re.search(r'(?ms)^RUN set -eu;.*?(?=^[A-Z]+\s)', dockerfile)
    assert block is not None
    script = block.group()[4:].replace('\\\n', '')
    commands = tmp_path / 'commands'
    commands.mkdir()
    log = tmp_path / 'apt.jsonl'
    mocks = {
        'dpkg-query': """import json, os, sys
versions = json.loads(os.environ['MCJ_TEST_PACKAGE_VERSIONS'])
if sys.argv[-1] not in versions:
    raise SystemExit(1)
print(versions[sys.argv[-1]], end='')
""",
        'apt-get': """import json, os, sys
with open(os.environ['MCJ_TEST_APT_LOG'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if os.environ.get('MCJ_TEST_APT_FAIL') in sys.argv[1:]:
    raise SystemExit(73)
""",
        'sed': 'pass\n',
        'rm': 'pass\n',
    }
    for name, content in mocks.items():
        path = commands / name
        path.write_text(f'#!{sys.executable}\n' + content)
        path.chmod(0o755)
    env = {
        **os.environ,
        'PATH': str(commands) + os.pathsep + os.environ.get('PATH', ''),
        'MCJ_TEST_PACKAGE_VERSIONS': json.dumps(versions),
        'MCJ_TEST_APT_LOG': str(log),
        'MCJ_TEST_APT_FAIL': fail_command,
    }
    result = subprocess.run(['/bin/sh', '-c', script], env=env, capture_output=True, text=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return result, calls


@pytest.mark.parametrize('versions,expected', [
    (OLDER, list(MINIMUM)),
    (MINIMUM, []),
    (NEWER, []),
    ({**NEWER, 'apt': OLDER['apt']}, ['apt']),
])
def test_only_older_packages_are_upgraded(tmp_path, versions, expected):
    result, calls = run_package_step(tmp_path, versions)
    assert result.returncode == 0, result.stderr
    if not expected:
        assert calls == []
        return
    assert calls == [
        ['-o', 'Acquire::Retries=0', 'update'],
        ['-o', 'Acquire::Retries=0', 'install', '--only-upgrade', '--no-install-recommends', '-y']
        + [f'{name}={MINIMUM[name]}' for name in expected],
    ]


@pytest.mark.parametrize('versions', [
    {'apt': MINIMUM['apt']},
    {**MINIMUM, 'apt': 'not-a-version'},
])
def test_unverifiable_package_state_stops_before_installation(tmp_path, versions):
    result, calls = run_package_step(tmp_path, versions)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize('command', ['update', 'install'])
def test_package_manager_failure_is_not_ignored(tmp_path, command):
    result, calls = run_package_step(tmp_path, OLDER, fail_command=command)
    assert result.returncode == 73
    assert calls[-1][2] == command


def test_base_images_are_directly_visible_to_dependency_updates():
    instructions = [line.split() for line in (ROOT / 'Dockerfile').read_text().splitlines()
                    if line.startswith('FROM ')]
    assert len(instructions) == 3
    for instruction in instructions:
        assert re.fullmatch(r'[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}', instruction[1])
    assert instructions[0][2:] == ['AS', 'docker_cli']
    assert instructions[1][2:] == ['AS', 'compose_security']

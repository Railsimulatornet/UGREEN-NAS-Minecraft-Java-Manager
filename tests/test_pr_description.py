"""Exercise the actual metadata-only workflow with synthetic PR descriptions."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


WORKFLOW_PATH = Path(__file__).parents[1] / '.github/workflows/pr-description.yml'
WORKFLOW = yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))
RUN = WORKFLOW['jobs']['description']['steps'][0]['run']
SOURCE = RUN.split("python3 -I - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


def check_description(tmp_path, *, title='Verbesserung', body='', author='ExampleOwner', kind='User'):
    event = tmp_path / 'event.json'
    event.write_text(json.dumps({'pull_request': {
        'title': title, 'body': body, 'user': {'login': author, 'type': kind},
    }}), encoding='utf-8')
    environment = dict(os.environ, GITHUB_EVENT_NAME='pull_request_target', GITHUB_EVENT_PATH=str(event))
    return subprocess.run([sys.executable, '-I', '-c', SOURCE], env=environment,
                          capture_output=True, text=True, timeout=5, check=False)


@pytest.mark.parametrize('body', [
    'Anmeldung nach Paketupdates repariert. Lokal geprüft.',
    'Python 3.15.2, Docker 29.9.2 und Compose aktualisieren.',
    'Die Dateien mcj/auth.py und .github/workflows/image.yml werden geprüft.',
    'Standardport 8090; Beispiel https://example.org/docs und 203.0.113.10.',
    'Version 1.0.2; die Installation verwendet /opt/mcj und localhost.',
    'Commit-Beschreibungen verständlicher formulieren.',
    'Die Oberfläche bleibt blau (#abcdef).',
    'Stand: 23.11.2026. Version 1.0.2 wurde geprüft.',
    'Quellstand vom 23.11.2026 geprüft.',
    'Beispiel http://[::ffff:203.0.113.10]/ für die Dokumentation.',
    None,
])
def test_ordinary_product_and_version_text_passes(tmp_path, body):
    result = check_description(tmp_path, body=body)
    assert result.returncode == 0
    assert result.stderr == ''


@pytest.mark.parametrize('private_text', [
    'CVE-2099-12345',
    'cve&#45;2099&#45;12345',
    r'CVE\-2099\-12345',
    'Commit: abcdef1',
    'Head `1234abc`',
    'Merge: abcdef1',
    'Geprüfter Quellstand: `abc1234`.',
    'SHA256: ' + '12ab' * 16,
    'https://github.com/example/project/commit/abcdef1',
    'https://github.com/example/project/blob/abcdef1/README.md',
    'Prüfstand ' + 'abcd' * 10,
    'Ziel ist http://192.168.42.7:8090/',
    'Ziel ist 10.20.30.40.',
    'Ziel ist 172.20.0.15',
    'http://%31%39%32.%31%36%38.42.7/',
    'http://[fd12:3456::7]/',
    'http://[fe80::1234%eth0]/',
    'http://[::ffff:10.20.30.40]/',
    'http://[::ffff:a14:1e28]/',
    'lab-storage.internal',
    'lab-box.home.arpa',
    'Datei auf serv42.example.invalid',
    r'C:\Users\Example\private-report.txt',
    r'\\lab-host\private\report.txt',
    '/home/example/private-report.txt',
    '/volume9/private/report.txt',
    '/workspace/scratch/example/report.txt',
])
def test_internal_details_fail_without_echoing_input(tmp_path, private_text):
    marker = 'SYNTHETIC_PRIVATE_CONTENT'
    result = check_description(tmp_path, body=marker + ' ' + private_text)
    assert result.returncode == 1
    assert result.stdout == '::error::Bitte Titel und Beschreibung kurz halten und interne Angaben entfernen.\n'
    assert result.stderr == ''
    assert marker not in result.stdout + result.stderr
    assert private_text not in result.stdout + result.stderr


def test_title_is_checked_too(tmp_path):
    result = check_description(tmp_path, title='Bericht von lab-storage.local', body='Geprüft.')
    assert result.returncode == 1
    assert 'lab-storage.local' not in result.stdout + result.stderr


@pytest.mark.parametrize('author,kind', [('dependabot[bot]', 'Bot'), ('github-actions[bot]', 'Bot')])
def test_bot_release_notes_have_real_success_without_echo(tmp_path, author, kind):
    result = check_description(tmp_path, body='CVE-2099-12345 ' + 'abcd' * 10,
                               author=author, kind=kind)
    assert result.returncode == 0
    assert 'CVE-' not in result.stdout + result.stderr
    assert 'abcd' not in result.stdout + result.stderr


def test_pr_text_is_data_and_cannot_execute_shell(tmp_path):
    target = tmp_path / 'must-not-exist'
    result = check_description(tmp_path, body=f'$(touch {target}) `touch {target}`')
    assert result.returncode == 1  # The path is private; the shell text remains data.
    assert not target.exists()
    assert str(target) not in result.stdout + result.stderr


def test_manual_selfcheck_passes_without_pr_event(tmp_path):
    environment = dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_EVENT_PATH=str(tmp_path/'absent'))
    result = subprocess.run([sys.executable, '-I', '-c', SOURCE], env=environment,
                            capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode == 0
    assert result.stdout == 'Selbstprüfung erfolgreich.\n'
    assert result.stderr == ''


def test_malformed_event_fails_without_details(tmp_path):
    event = tmp_path / 'event.json'
    event.write_text('{SYNTHETIC_PRIVATE_CONTENT', encoding='utf-8')
    environment = dict(os.environ, GITHUB_EVENT_NAME='pull_request_target', GITHUB_EVENT_PATH=str(event))
    result = subprocess.run([sys.executable, '-I', '-c', SOURCE], env=environment,
                            capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode == 1
    assert result.stderr == ''
    assert 'SYNTHETIC_PRIVATE_CONTENT' not in result.stdout


@pytest.mark.parametrize('body', [0, False, [], {'unexpected': 'SYNTHETIC_PRIVATE_CONTENT'}])
def test_unexpected_body_type_fails_without_details(tmp_path, body):
    result = check_description(tmp_path, body=body)
    assert result.returncode == 1
    assert result.stderr == ''
    assert 'SYNTHETIC_PRIVATE_CONTENT' not in result.stdout


def test_workflow_needs_no_checkout_actions_secrets_or_write_rights():
    assert WORKFLOW['permissions'] == {}
    steps = WORKFLOW['jobs']['description']['steps']
    assert len(steps) == 1
    assert 'uses' not in steps[0]
    assert '${{' not in RUN
    assert 'secrets.' not in WORKFLOW_PATH.read_text(encoding='utf-8')
    events = WORKFLOW.get('on', WORKFLOW.get(True))
    assert events['pull_request_target']['types'] == ['opened', 'edited', 'reopened', 'synchronize']

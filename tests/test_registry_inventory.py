"""Keep registry inventory read-only and reject unverified metadata."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def inventory(monkeypatch):
    path = Path(__file__).parents[1] / '.github/scripts/registry_inventory.py'
    spec = importlib.util.spec_from_file_location('registry_inventory', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('REGISTRY_USERNAME', 'fixture')
    monkeypatch.setenv('REGISTRY_TOKEN', 'fixture-token')
    return module


def test_inventory_verifies_manifest_without_pulling_layers(inventory, monkeypatch, tmp_path):
    calls = []
    config_id = 'sha256:' + 'a' * 64
    raw = json.dumps({'config': {'digest': config_id}}).encode()
    digest = 'sha256:' + hashlib.sha256(raw).hexdigest()

    def request(url, headers):
        calls.append(url)
        if url.startswith('https://auth.docker.io/token?'):
            return {'token': 'fixture-bearer'}, {}, b''
        if '/tags/list?' in url:
            return {'tags': ['1.0.0', 'stable']}, {}, b''
        assert '/manifests/' in url
        assert headers['Authorization'] == 'Bearer fixture-bearer'
        return json.loads(raw), {'Docker-Content-Digest': digest}, raw

    monkeypatch.setattr(inventory, 'request', request)
    monkeypatch.setattr(inventory, 'Path', lambda unused: tmp_path / 'report.json')
    inventory.main()
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['tag_count'] == 2
    assert {row['image_config_id'] for row in report['tags']} == {config_id}
    assert not report['images_pulled'] and not report['images_pushed'] and not report['images_deleted']
    assert len(calls) == 4
    assert 'fixture-token' not in (tmp_path / 'report.json').read_text()


@pytest.mark.parametrize('next_page', ['https://example.invalid/v2/repo/tags/list?n=100',
                                       'http://registry-1.docker.io/v2/repo/tags/list?n=100'])
def test_inventory_rejects_external_pagination_before_sending_credentials(inventory, monkeypatch, next_page):
    calls = []

    def request(url, headers):
        calls.append(url)
        if url.startswith('https://auth.docker.io/token?'):
            return {'token': 'fixture-bearer'}, {}, b''
        return {'tags': []}, {'Link': '<' + next_page + '>; rel="next"'}, b''

    monkeypatch.setattr(inventory, 'request', request)
    with pytest.raises(ValueError, match='pagination'):
        inventory.main()
    assert len(calls) == 2


def test_inventory_rejects_manifest_digest_mismatch(inventory, monkeypatch):
    def request(url, headers):
        if url.startswith('https://auth.docker.io/token?'):
            return {'token': 'fixture-bearer'}, {}, b''
        if '/tags/list?' in url:
            return {'tags': ['stable']}, {}, b''
        return {'config': {'digest': 'sha256:' + 'a' * 64}}, {'Docker-Content-Digest': 'sha256:' + 'b' * 64}, b'{}'

    monkeypatch.setattr(inventory, 'request', request)
    with pytest.raises(ValueError, match='digest mismatch'):
        inventory.main()

import importlib.util
import hashlib
from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('release_metadata', ROOT / '.github/scripts/release_metadata.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
REVISION = 'a' * 40


def test_later_version_is_read_without_importing_application_code(tmp_path):
    (tmp_path / 'mcj').mkdir()
    (tmp_path / 'mcj/__init__.py').write_text("__version__ = '1.2.3'\nraise RuntimeError('must not execute')\n")
    assert release.version(tmp_path) == '1.2.3'
    assert release.tags('1.2.3', REVISION, 'refs/tags/v1.2.3') == ['sha-' + REVISION, '1.2.3', 'stable']


@pytest.mark.parametrize('value', ["__version__='1.0'", "__version__='01.0.0'", "__version__='1.0.0-rc1'", "__version__='1.0.0'\n__version__='1.0.1'", "__version__=None"])
def test_invalid_or_ambiguous_release_version_is_refused(tmp_path, value):
    (tmp_path / 'mcj').mkdir()
    (tmp_path / 'mcj/__init__.py').write_text(value)
    with pytest.raises(ValueError):
        release.version(tmp_path)


def test_official_tags_require_matching_version_and_approved_source():
    assert release.tags('1.0.0', REVISION, 'refs/heads/main') == ['sha-' + REVISION, 'edge']
    assert release.tags('1.0.0', REVISION, 'refs/heads/main', True) == ['sha-' + REVISION, '1.0.0', 'stable']
    assert release.tags('1.0.0', REVISION, 'refs/heads/feature') == ['sha-' + REVISION]
    with pytest.raises(ValueError):
        release.tags('1.0.0', REVISION, 'refs/tags/v1.0.1')
    with pytest.raises(ValueError):
        release.tags('1.0.0', REVISION, 'refs/heads/feature', True)
    with pytest.raises(ValueError):
        release.tags('1.0.0', 'short', 'refs/heads/main', True)


def test_release_version_agrees_with_installation_and_display_metadata():
    current = release.version(ROOT)
    assert 'ARG APP_VERSION=' + current in (ROOT / 'Dockerfile').read_text()
    assert '**Version ' + current + '**' in (ROOT / 'README.md').read_text(encoding='utf-8')
    assert '## ' + current + ' ' in (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    setup = yaml.safe_load((ROOT / 'deploy/ugos-einrichtung.yaml').read_text(encoding='utf-8'))
    assert setup['services']['einrichtung']['image'].endswith(':' + current)
    compose = (ROOT / 'compose.yaml').read_text()
    assert 'mcj-manager:' + current in compose
    assert 'class="version">v' + current + '</span>' in (ROOT / 'mcj/static/index.html').read_text()
    assert set(re.findall(r'"internalOnly": "Version ([0-9.]+)"', (ROOT / 'mcj/static/i18n.js').read_text(encoding='utf-8'))) == {current}
    workflow = yaml.safe_load((ROOT / '.github/workflows/image.yml').read_text(encoding='utf-8'))
    build = workflow['jobs']['build']['steps']
    assert any(s.get('run') == 'python3 .github/scripts/release_metadata.py' for s in build)
    assert any('APP_VERSION=${{ steps.release.outputs.version }}' in s.get('with', {}).get('build-args', '') for s in build)
    publish = workflow['jobs']['publish']['steps']
    load = next(s for s in publish if s.get('name') == 'Verify and load tested archive')
    assert 'org.opencontainers.image.version' in load['run'] and 'org.opencontainers.image.revision' in load['run']


def test_provider_identity_uses_the_project_version_and_public_project_url():
    from mcj import __version__, mods, sources, versions
    from mcj.http_identity import AGENT, PROJECT_URL
    assert mods.AGENT == sources.AGENT == versions.AGENT == AGENT
    assert '/' + __version__ + ' (' + PROJECT_URL + ')' in AGENT
    assert PROJECT_URL == 'https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager'
    assert '@' not in AGENT


def test_setup_image_identity_follows_the_installed_project_version(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT / 'tools'))
    import ugos_prepare
    monkeypatch.setattr(ugos_prepare, '__version__', '1.0.1')
    identifier = 'sha256:' + 'a' * 64
    image = {'Id': identifier, 'Config': {'Labels': {'org.opencontainers.image.version': '1.0.1', 'org.opencontainers.image.revision': REVISION}}}
    assert ugos_prepare.image_identity('mcj-manager:1.0.1', {'Image': identifier}, image) == identifier
    image['Config']['Labels']['org.opencontainers.image.version'] = '1.0.0'
    with pytest.raises(RuntimeError, match='setup_release_image_unverified'):
        ugos_prepare.image_identity('mcj-manager:1.0.1', {'Image': identifier}, image)


def test_docker_cli_original_notices_are_in_the_image_build_context():
    expected = {'LICENSE': '2d81ea060825006fc8f3fe28aa5dc0ffeb80faf325b612c955229157b8c10dc0',
                'NOTICE': 'a8c869fbda819afb8d80e0ac19bac52e766bc6c19cb38cf94f52d64c4be2aab6'}
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / 'licenses/docker-cli' / name).read_bytes()).hexdigest() == digest
    assert '!licenses/**' in (ROOT / '.dockerignore').read_text()
    assert 'COPY --chown=0:10 licenses /opt/mcj/licenses' in (ROOT / 'Dockerfile').read_text()


def test_public_sources_match_the_two_shipped_guard_variants():
    assert (ROOT / 'guard-neoforge').is_dir()
    assert (ROOT / 'guard-neoforge-1211').is_dir()
    assert not (ROOT / 'guard').exists() and not (ROOT / 'guard-fabric').exists()

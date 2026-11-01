import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).parents[1] / '.github/scripts/publish_tested_image.py')
publisher = importlib.util.module_from_spec(spec); spec.loader.exec_module(publisher)


def test_only_exact_release_tags_and_full_commit_are_accepted():
    rev = 'a' * 40
    tags = ['sha-' + rev, '1.0.0', 'stable']
    assert publisher.allowed_tags('1.0.0', rev, tags) == tags
    for invalid in [tags + ['edge'], ['sha-' + rev, 'v1.0.0', 'stable'], ['2026-11-01', 'stable']]:
        with pytest.raises(ValueError):publisher.allowed_tags('1.0.0', rev, invalid)
    with pytest.raises(ValueError):publisher.allowed_tags('1.0.0', 'short', tags)


def test_unexpected_index_cannot_replace_a_verified_single_platform_image():
    digest = 'sha256:' + 'b' * 64
    assert publisher.manifest_config({'config': {'digest': digest}}) == digest
    for invalid in [{'manifests': []}, {'config': {'digest': 'unknown'}}]:
        with pytest.raises(ValueError):publisher.manifest_config(invalid)

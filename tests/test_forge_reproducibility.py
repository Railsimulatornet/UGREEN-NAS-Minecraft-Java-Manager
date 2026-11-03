import hashlib
import json
from collections import Counter
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / 'artifacts/compatibility/forge-1201-reproducibility.json'


def contents(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        return {item.filename: archive.read(item) for item in archive.infolist() if not item.is_dir()}


def equivalent(previous, current):
    assert previous.keys() == current.keys()
    for name, raw in previous.items():
        if name == 'mcj_guard.refmap.json':
            assert json.loads(raw) == json.loads(current[name])
        elif name == 'mcj_guard-shadow.srg':
            assert Counter(raw.splitlines()) == Counter(current[name].splitlines())
        else:
            assert raw == current[name], name


def test_rebuilt_guard_preserves_every_class_manifest_and_mapping():
    proof = json.loads(PROOF.read_text())
    old = ROOT / 'artifacts' / proof['previous']['filename']
    new = ROOT / 'artifacts' / proof['current']['filename']
    for key, path in [('previous', old), ('current', new)]:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == proof[key]['sha256']
    equivalent(contents(old), contents(new))
    assert len(proof['builds']) == 2
    assert all(b['result'] == 'passed' and b['sha256'] == proof['current']['sha256'] for b in proof['builds'])
    assert proof['build_environment']['independent_workspaces_and_caches'] is True
    module = ROOT / proof['module']
    sources = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in module.rglob('*') if p.is_file()
               and not any(part in {'.gradle', 'build', '__pycache__'} for part in p.relative_to(module).parts)}
    assert hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest() == proof['source_sha256']
    for entry in proof['equivalence']['entries']:
        assert hashlib.sha256(contents(old)[entry['name']]).hexdigest() == entry['previous_sha256']
        assert hashlib.sha256(contents(new)[entry['name']]).hexdigest() == entry['current_sha256']


@pytest.mark.parametrize('mutation', ['class', 'manifest', 'resource', 'mapping_value', 'missing_entry', 'duplicate_srg'])
def test_acceptance_reuse_rejects_behavioral_or_mapping_changes(mutation):
    proof = json.loads(PROOF.read_text())
    old = contents(ROOT / 'artifacts' / proof['previous']['filename'])
    changed = dict(old)
    if mutation in ['class', 'manifest', 'resource']:
        name = next(n for n in old if n.endswith('.class')) if mutation == 'class' else 'META-INF/MANIFEST.MF' if mutation == 'manifest' else 'META-INF/mods.toml'
        changed[name] += b'changed'
    elif mutation == 'mapping_value':
        value = json.loads(old['mcj_guard.refmap.json']); value['unexpected'] = 'changed'
        changed['mcj_guard.refmap.json'] = json.dumps(value).encode()
    elif mutation == 'missing_entry':
        del changed[next(iter(changed))]
    else:
        changed['mcj_guard-shadow.srg'] += old['mcj_guard-shadow.srg'].splitlines()[0] + b'\n'
    with pytest.raises(AssertionError):
        equivalent(old, changed)


def test_reused_native_acceptance_keeps_the_original_artifact_identity():
    path = ROOT / 'artifacts/guard-acceptance-forge-repro-20261103.json'
    record = json.loads(path.read_text())
    original_path = ROOT / record['previous_acceptance']['scope']
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == record['previous_acceptance']['sha256']
    assert hashlib.sha256(PROOF.read_bytes()).hexdigest() == record['equivalence']['sha256']
    original = json.loads(original_path.read_text())
    assert record['native_tests_repeated'] is False and len(record['configurations']) == 2
    for current in record['configurations']:
        previous = next(x for x in original['configurations'] if (x['minecraft'], x['loader']) == (current['minecraft'], current['loader']))
        assert current['original_guard_sha256'] == previous['guard_sha256']
        assert current['server_log_sha256'] == previous['server_log_sha256']
        assert current['regular_server_log_sha256'] == previous['regular_server_log_sha256']
        for case in current['client_cases']:
            assert case['original_guard_sha256'] == previous['guard_sha256'] and case['execution'] == 'reused'

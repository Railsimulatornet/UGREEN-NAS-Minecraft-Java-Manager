import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'dependabot_patch_merge.py'
if not SOURCE.exists():
    SOURCE = ROOT.parents[0] / '.github/scripts/dependabot_patch_merge.py'
spec = importlib.util.spec_from_file_location('dependency_automation', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE = 'a' * 40
HEAD = 'b' * 40


def pr():
    return {'number': 9, 'state': 'open', 'draft': False,
            'user': {'id': 49699333, 'login': 'dependabot[bot]'},
            'base': {'ref': 'main', 'sha': BASE, 'repo': {'id': 1441216330}},
            'head': {'ref': 'dependabot/pip/python-test', 'sha': HEAD, 'repo': {'id': 1441216330}}}


def checks():
    values = [{'name': f'guard ({i})', 'app': {'id': 15368}} for i in range(8)]
    values += [{'name': name, 'app': {'id': app}} for name, app in
               [('tests', 15368), ('analyze (python)', 15368),
                ('analyze (javascript-typescript)', 15368), ('CodeQL', 57789)]]
    return [dict(v, status='completed', conclusion='success') for v in values]


class FakeGitHub:
    def __init__(self):
        self.current = pr()
        self.old = 'pydantic==2.14.2\n'
        self.new = 'pydantic==2.14.3\n'
        self.checks = checks()
        self.files = [{'filename': f, 'status': 'modified'} for f in sorted(m.FILES)]
        self.mutations = []
        self.rereads = 0
        self.change_head = False

    def contents(self, path, sha):
        assert path in m.FILES
        return self.old if sha == BASE else self.new

    def pages(self, path, key=None):
        if path.startswith('/pulls?'):
            return [{'number': 9}]
        if path == '/pulls/9/files':
            return copy.deepcopy(self.files)
        if '/check-runs?' in path:
            assert HEAD in path
            return copy.deepcopy(self.checks)
        raise AssertionError(path)

    def request(self, path, method='GET', data=None):
        if method != 'GET':
            self.mutations.append((path, method, data))
            return {'merged': True, 'sha': 'c' * 40}
        if path == '/pulls/9':
            self.rereads += 1
            value = copy.deepcopy(self.current)
            if self.change_head and self.rereads > 1:
                value['head']['sha'] = 'd' * 40
            return value
        if path == '/git/ref/heads/main':
            return {'object': {'sha': BASE}}
        if path.endswith('/status'):
            return {'total_count': 0, 'state': 'pending'}
        raise AssertionError(path)


class PatchUpdateTests(unittest.TestCase):
    def test_valid_patch_keeps_platform_marker(self):
        old = 'typing-inspection==0.4.4; python_version >= "3.10"\n'
        new = 'typing-inspection==0.4.5; python_version >= "3.10"\n'
        self.assertEqual(m.patch_changes(old, new), {'typing-inspection': ('0.4.4', '0.4.5')})

    def test_minor_major_downgrade_and_prerelease_stay_manual(self):
        for old, new in [('4.15.1', '4.16.0'), ('4.15.1', '5.0.0'),
                         ('4.15.1', '4.15.0'), ('4.15.1', '4.15.2rc1')]:
            self.assertIsNone(m.patch_changes('anyio==' + old, 'anyio==' + new))

    def test_new_dependency_extra_index_flags_comments_or_markers_not_accepted(self):
        original = 'pydantic==2.14.2\n'
        for after in ['pydantic==2.14.3\nother==1.0.0\n', '--extra-index-url https://example.invalid\n',
                      'pydantic==2.14.3 --hash=anything\n', 'pydantic==2.14.3; sys_platform == "win32"\n',
                      '# no longer installed\n', 'unknown==2.14.3\n']:
            self.assertIsNone(m.patch_changes(original, after))

    def test_lookalike_actor_fork_old_base_and_draft_rejected(self):
        self.assertTrue(m.trusted_pr(pr(), BASE))
        for mutate in [lambda p: p['user'].update(id=123),
                       lambda p: p['head']['repo'].update(id=123),
                       lambda p: p['base'].update(sha='e' * 40),
                       lambda p: p.update(draft=True),
                       lambda p: p['head'].update(ref='feature/update')]:
            value = pr();mutate(value)
            self.assertFalse(m.trusted_pr(value, BASE))

    def test_failed_pending_skipped_guard_or_missing_analysis_blocks(self):
        self.assertTrue(m.checks_ready(checks(), {'total_count': 0}))
        for conclusion in ['failure', 'cancelled', 'timed_out', 'skipped']:
            value = checks();value[0]['conclusion'] = conclusion
            self.assertFalse(m.checks_ready(value, {'total_count': 0}))
        value = checks();value[-1]['status'] = 'in_progress'
        self.assertFalse(m.checks_ready(value, {'total_count': 0}))
        self.assertFalse(m.checks_ready(checks()[:-1], {'total_count': 0}))
        self.assertFalse(m.checks_ready(checks(), {'total_count': 1, 'state': 'failure'}))

    def test_check_name_from_wrong_app_is_not_enough(self):
        for index in [0, 8, 11]:
            value = checks();value[index]['app']['id'] = 123
            self.assertFalse(m.checks_ready(value, {'total_count': 0}))

    def test_optional_publish_jobs_may_be_skipped(self):
        value = checks() + [{'name': 'publish', 'status': 'completed', 'conclusion': 'skipped'}]
        self.assertTrue(m.checks_ready(value, {'total_count': 0}))

    def test_dry_run_never_merges(self):
        api = FakeGitHub()
        self.assertEqual(m.run(api)[0]['result'], 'Patchupdate freigabefähig')
        self.assertEqual(api.mutations, [])

    def test_eligible_merge_is_bound_to_exact_head(self):
        api = FakeGitHub();result = m.run(api, dry_run=False)
        self.assertEqual(result[0]['result'], 'Patchupdate übernommen')
        self.assertEqual(api.mutations[0][2]['sha'], HEAD)
        self.assertEqual(api.mutations[0][2]['merge_method'], 'squash')

    def test_new_head_after_checks_is_not_merged(self):
        api = FakeGitHub();api.change_head = True
        self.assertEqual(m.run(api, dry_run=False)[0]['result'], 'Stand zwischenzeitlich geändert')
        self.assertEqual(api.mutations, [])

    def test_extra_file_and_failed_build_are_never_merged(self):
        for mode in ['file', 'failure']:
            api = FakeGitHub()
            if mode == 'file':api.files.append({'filename': 'mcj/auth.py', 'status': 'modified'})
            else:api.checks[0]['conclusion'] = 'failure'
            m.run(api, dry_run=False)
            self.assertEqual(api.mutations, [])

    def test_runtime_and_development_locks_must_match(self):
        api = FakeGitHub();original = api.contents
        api.contents = lambda path, sha: 'pydantic==2.14.4\n' if path == 'requirements-dev.txt' and sha == HEAD else original(path, sha)
        self.assertIsNone(m.evaluate(api, pr(), BASE))


if __name__ == '__main__':
    unittest.main()

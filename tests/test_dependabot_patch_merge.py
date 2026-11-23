import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'dependabot_patch_merge.py'
if not SOURCE.exists():
    SOURCE = ROOT.parents[0] / '.github/scripts/dependabot_patch_merge.py'
spec = importlib.util.spec_from_file_location('dependency_automation', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE = 'a' * 40
HEAD = 'b' * 40
MERGED = 'c' * 40


def statuses():
    return {'sha': HEAD, 'total_count': 0, 'state': 'pending'}


def pr():
    return {'number': 9, 'state': 'open', 'draft': False,
            'user': {'id': 49699333, 'login': 'dependabot[bot]'},
            'base': {'ref': 'main', 'sha': BASE, 'repo': {'id': 1441216330}},
            'head': {'ref': 'dependabot/pip/python-test', 'sha': HEAD, 'repo': {'id': 1441216330}}}


def checks():
    values = [{'name': f'guard ({adapter}, source, manifest, image)', 'app': {'id': 15368}}
              for adapter in sorted(m.GUARDS)]
    values += [{'name': name, 'app': {'id': app}} for name, app in
               [('tests', 15368), ('build', 15368), ('analyze (python)', 15368),
                ('analyze (javascript-typescript)', 15368), ('CodeQL', 57789)]]
    return [dict(v, head_sha=HEAD, status='completed', conclusion='success') for v in values]


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
        self.change_main = False
        self.check_rereads = 0
        self.change_checks = False
        self.comparison = {'merge_base_commit': {'sha': BASE}, 'behind_by': 0, 'status': 'ahead'}
        self.statuses = statuses()
        self.merge_result = {'merged': True, 'sha': MERGED}
        self.dispatch_failures = set()

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
            self.check_rereads += 1
            value = copy.deepcopy(self.checks)
            if self.change_checks and self.check_rereads > 1:
                value[0].update(status='in_progress', conclusion=None)
            return value
        raise AssertionError(path)

    def request(self, path, method='GET', data=None):
        if method != 'GET':
            self.mutations.append((path, method, data))
            if path == '/pulls/9/merge' and method == 'PUT':
                return copy.deepcopy(self.merge_result)
            if path.startswith('/actions/workflows/') and path.endswith('/dispatches') and method == 'POST':
                if path.split('/')[-2] in self.dispatch_failures:
                    raise RuntimeError('Simulated dispatch failure')
                return None
            raise AssertionError((path, method, data))
        if path == '/pulls/9':
            self.rereads += 1
            value = copy.deepcopy(self.current)
            if self.change_head and self.rereads > 1:
                value['head']['sha'] = 'd' * 40
            if self.change_main and self.rereads > 1:
                value['base']['sha'] = 'e' * 40
            return value
        if path == '/git/ref/heads/main':
            return {'object': {'sha': 'e' * 40 if self.change_main and self.rereads > 1 else BASE}}
        if path == f'/compare/{BASE}...{HEAD}':
            return copy.deepcopy(self.comparison)
        if path.endswith('/status'):
            return copy.deepcopy(self.statuses)
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
        self.assertTrue(m.checks_ready(checks(), statuses(), HEAD))
        for conclusion in ['failure', 'cancelled', 'timed_out', 'skipped', 'neutral']:
            value = checks();value[0]['conclusion'] = conclusion
            self.assertFalse(m.checks_ready(value, statuses(), HEAD))
        value = checks();value[-1]['status'] = 'in_progress'
        self.assertFalse(m.checks_ready(value, statuses(), HEAD))
        self.assertFalse(m.checks_ready(checks()[:-1], statuses(), HEAD))
        self.assertFalse(m.checks_ready(checks(), dict(statuses(), total_count=1, state='failure'), HEAD))

    def test_check_name_from_wrong_app_is_not_enough(self):
        for index in range(len(checks())):
            value = checks();value[index]['app']['id'] = 123
            self.assertFalse(m.checks_ready(value, statuses(), HEAD))

    def test_each_required_check_must_belong_to_head_and_be_completed_successfully(self):
        for index in range(len(checks())):
            for field, wrong in [('head_sha', 'e' * 40), ('status', 'queued'),
                                 ('conclusion', 'skipped'), ('conclusion', 'neutral')]:
                with self.subTest(check=checks()[index]['name'], field=field, wrong=wrong):
                    value = checks();value[index][field] = wrong
                    self.assertFalse(m.checks_ready(value, statuses(), HEAD))

    def test_build_cannot_be_missing_or_replaced_by_a_duplicate_check(self):
        value = [row for row in checks() if row['name'] != 'build']
        self.assertFalse(m.checks_ready(value, statuses(), HEAD))
        value = checks();value.append(copy.deepcopy(next(row for row in value if row['name'] == 'build')))
        self.assertFalse(m.checks_ready(value, statuses(), HEAD))

    def test_guard_adapter_set_must_be_complete_and_unique(self):
        for name in ['guard (unknown, source)', 'guard (', checks()[1]['name']]:
            with self.subTest(name=name):
                value = checks();value[0]['name'] = name
                self.assertFalse(m.checks_ready(value, statuses(), HEAD))
        value = checks()
        for row in value[:8]:row['name'] = 'guard (forge-1211, duplicate)'
        self.assertFalse(m.checks_ready(value, statuses(), HEAD))

    def test_commit_status_must_be_complete_and_belong_to_the_same_head(self):
        for value in [{}, dict(statuses(), sha='e' * 40), dict(statuses(), total_count=-1),
                      dict(statuses(), total_count=1, state='pending')]:
            self.assertFalse(m.checks_ready(checks(), value, HEAD))
        self.assertTrue(m.checks_ready(checks(), dict(statuses(), total_count=1, state='success'), HEAD))

    def test_optional_publish_jobs_may_be_skipped(self):
        value = checks() + [{'name': 'publish', 'status': 'completed', 'conclusion': 'skipped'}]
        self.assertTrue(m.checks_ready(value, statuses(), HEAD))

    def test_dry_run_never_merges(self):
        api = FakeGitHub()
        self.assertEqual(m.run(api)[0]['result'], 'Patchupdate freigabefähig')
        self.assertEqual(api.mutations, [])

    def test_eligible_merge_is_bound_to_exact_head(self):
        api = FakeGitHub();result = m.run(api, dry_run=False)
        self.assertEqual(result[0]['result'], 'Patchupdate übernommen')
        self.assertEqual(api.mutations[0][2]['sha'], HEAD)
        self.assertEqual(api.mutations[0][2]['merge_method'], 'squash')

    def test_real_ancestry_is_required_even_when_pull_request_base_matches_main(self):
        for comparison in [dict(merge_base_commit={'sha': 'e' * 40}, behind_by=0, status='ahead'),
                           dict(merge_base_commit={'sha': BASE}, behind_by=1, status='diverged'),
                           dict(merge_base_commit={'sha': BASE}, behind_by=0, status='diverged'), {}]:
            with self.subTest(comparison=comparison):
                api = FakeGitHub();api.comparison = comparison
                self.assertIsNone(m.evaluate(api, pr(), BASE))
                self.assertEqual(api.mutations, [])

    def test_new_main_after_checks_is_not_merged_even_if_pr_base_was_updated(self):
        api = FakeGitHub();api.change_main = True
        self.assertEqual(m.run(api, dry_run=False)[0]['result'], 'Stand zwischenzeitlich geändert')
        self.assertEqual(api.mutations, [])

    def test_same_head_checks_are_rechecked_before_merge(self):
        api = FakeGitHub();api.change_checks = True
        self.assertEqual(m.run(api, dry_run=False)[0]['result'], 'Prüfungen zwischenzeitlich geändert')
        self.assertEqual(api.mutations, [])

    def test_confirmed_merge_requests_both_sha_bound_checks_without_publication(self):
        api = FakeGitHub();result = m.run(api, dry_run=False)[0]
        self.assertEqual(result['head_sha'], HEAD)
        self.assertEqual(result['sha'], MERGED)
        self.assertEqual(result['post_merge_checks']['state'], 'angefordert, noch nicht bestätigt')
        dispatches = {path: data for path, method, data in api.mutations if method == 'POST'}
        self.assertEqual(set(dispatches), {'/actions/workflows/image.yml/dispatches',
                                          '/actions/workflows/codeql.yml/dispatches'})
        self.assertEqual(dispatches['/actions/workflows/image.yml/dispatches'], {
            'ref': 'main', 'inputs': {'expected_revision': MERGED, 'build_image': True,
                                    'full_validation': True, 'publish_image': False,
                                    'installation_tags': False, 'anonymous_installation': False}})
        self.assertEqual(dispatches['/actions/workflows/codeql.yml/dispatches'], {
            'ref': 'main', 'inputs': {'expected_revision': MERGED}})

    def test_unconfirmed_merge_does_not_request_post_merge_checks(self):
        for result in [{'merged': False, 'sha': MERGED}, {'merged': True, 'sha': 'invalid'}]:
            api = FakeGitHub();api.merge_result = result
            with self.assertRaisesRegex(RuntimeError, 'nicht bestätigt'):
                m.run(api, dry_run=False)
            self.assertEqual(len(api.mutations), 1)

    def test_failed_dispatch_preserves_merge_identity_and_attempts_other_workflow(self):
        api = FakeGitHub();api.dispatch_failures = {'image.yml'}
        with self.assertRaisesRegex(RuntimeError, MERGED + ': Übernahme bestätigt'):
            m.run(api, dry_run=False)
        self.assertEqual(len(api.mutations), 3)
        self.assertEqual(api.mutations[-1][0], '/actions/workflows/codeql.yml/dispatches')

    def test_new_head_after_checks_is_not_merged(self):
        api = FakeGitHub();api.change_head = True
        self.assertEqual(m.run(api, dry_run=False)[0]['result'], 'Stand zwischenzeitlich geändert')
        self.assertEqual(api.mutations, [])

    def test_extra_file_and_failed_build_are_never_merged(self):
        for mode in ['file', 'failure']:
            api = FakeGitHub()
            if mode == 'file':api.files.append({'filename': 'mcj/auth.py', 'status': 'modified'})
            else:next(row for row in api.checks if row['name'] == 'build')['conclusion'] = 'failure'
            m.run(api, dry_run=False)
            self.assertEqual(api.mutations, [])

    def test_runtime_and_development_locks_must_match(self):
        api = FakeGitHub();original = api.contents
        api.contents = lambda path, sha: 'pydantic==2.14.4\n' if path == 'requirements-dev.txt' and sha == HEAD else original(path, sha)
        self.assertIsNone(m.evaluate(api, pr(), BASE))

    def test_workflow_dispatch_accepts_empty_204_response(self):
        with patch.object(m.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b''
            result = m.GitHub('unit-test-token').request('/actions/workflows/image.yml/dispatches',
                                                       method='POST', data={'ref': 'main'})
            self.assertIsNone(result)
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(request.full_url, 'https://api.github.com/repos/' + m.REPOSITORY +
                             '/actions/workflows/image.yml/dispatches')


if __name__ == '__main__':
    unittest.main()

"""Begrenzte Übernahme geprüfter Python-Patchupdates, ohne PR-Code auszuführen."""
import argparse
import base64
import json
import os
import re
import urllib.request

REPOSITORY = 'Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager'
REPOSITORY_ID = 1441216330
DEPENDABOT_ID = 49699333
PACKAGES = {'anyio', 'pydantic', 'pydantic-core', 'python-multipart', 'typing-inspection'}
FILES = {'requirements.txt', 'requirements-dev.txt'}
GUARDS = {'neoforge-263', 'neoforge-1211', 'fabric-1201', 'fabric-1211',
          'fabric-263', 'forge-1201', 'forge-1211', 'forge-263'}
PIN = re.compile(r'([A-Za-z0-9_.-]+)==(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(\s*;.*)?')


def patch_changes(before, after):
    old_lines, new_lines = before.splitlines(), after.splitlines()
    if len(old_lines) != len(new_lines):
        return None
    changes = {}
    for old, new in zip(old_lines, new_lines):
        if old == new:
            continue
        a, b = PIN.fullmatch(old), PIN.fullmatch(new)
        if not a or not b or a[1] != b[1] or a[5] != b[5]:
            return None
        name = re.sub(r'[-_.]+', '-', a[1]).lower()
        if name not in PACKAGES or (a[2], a[3]) != (b[2], b[3]) or int(b[4]) <= int(a[4]):
            return None
        value = ('.'.join(a[i] for i in range(2, 5)), '.'.join(b[i] for i in range(2, 5)))
        if name in changes and changes[name] != value:
            return None
        changes[name] = value
    return changes or None


def trusted_pr(pr, main_sha):
    return (
        pr.get('state') == 'open' and not pr.get('draft')
        and pr.get('user', {}).get('id') == DEPENDABOT_ID
        and pr.get('user', {}).get('login') == 'dependabot[bot]'
        and pr.get('base', {}).get('ref') == 'main'
        and pr.get('base', {}).get('repo', {}).get('id') == REPOSITORY_ID
        and pr.get('head', {}).get('repo', {}).get('id') == REPOSITORY_ID
        and pr.get('head', {}).get('ref', '').startswith('dependabot/pip/')
        and pr.get('base', {}).get('sha') == main_sha
        and bool(re.fullmatch(r'[0-9a-f]{40}', pr.get('head', {}).get('sha', '')))
    )


def checks_ready(checks, statuses, head_sha):
    def successful(row, app):
        return (row.get('head_sha') == head_sha and row.get('status') == 'completed'
                and row.get('conclusion') == 'success' and row.get('app', {}).get('id') == app)

    guards = [row for row in checks if row['name'].startswith('guard (')]
    adapters = [re.match(r'guard \(([^,\s)]+)(?:,|\))', row['name']) for row in guards]
    if (len(guards) != len(GUARDS) or any(match is None for match in adapters)
            or {match[1] for match in adapters} != GUARDS
            or any(not successful(row, 15368) for row in guards)):
        return False
    for name, app in [('tests', 15368), ('build', 15368), ('analyze (python)', 15368),
                      ('analyze (javascript-typescript)', 15368), ('CodeQL', 57789)]:
        rows = [row for row in checks if row['name'] == name]
        if len(rows) != 1 or not successful(rows[0], app):
            return False
    if any(row.get('status') != 'completed' or row.get('conclusion') not in
           {'success', 'skipped', 'neutral'} for row in checks):
        return False
    count = statuses.get('total_count')
    return (statuses.get('sha') == head_sha and type(count) is int and count >= 0
            and (count == 0 or statuses.get('state') == 'success'))


def head_checks_ready(api, head_sha):
    checks = api.pages(f'/commits/{head_sha}/check-runs?filter=latest', key='check_runs')
    statuses = api.request(f'/commits/{head_sha}/status')
    return checks_ready(checks, statuses, head_sha)


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, path, method='GET', data=None):
        # All callers use repository-relative paths, never URLs supplied by a PR.
        assert path.startswith('/') and not path.startswith('//') and '\n' not in path
        url = 'https://api.github.com/repos/' + REPOSITORY + path
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        request = urllib.request.Request(url, headers=headers, method=method,
                                        data=None if data is None else json.dumps(data).encode())
        # GitHub's API endpoints used here do not require redirects; avoid forwarding tokens.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            body = response.read()
            # workflow_dispatch confirms acceptance with HTTP 204 and no JSON body.
            return json.loads(body) if body else None

    def pages(self, path, key=None):
        rows = []
        for page in range(1, 11):
            value = self.request(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
            part = value if key is None else value[key]
            rows.extend(part)
            if len(part) < 100:
                return rows
        raise RuntimeError('Unvollständige GitHub-Antwort; keine Übernahme')

    def contents(self, path, sha):
        value = self.request('/contents/' + path + '?ref=' + sha)
        assert value['encoding'] == 'base64' and value['size'] < 100000
        return base64.b64decode(value['content'].replace('\n', ''), validate=True).decode('utf-8')


def evaluate(api, pr, main_sha):
    if not trusted_pr(pr, main_sha):
        return None
    number = int(pr['number'])
    files = api.pages(f'/pulls/{number}/files')
    if (len(files) != len(FILES) or {row['filename'] for row in files} != FILES
            or any(row['status'] != 'modified' for row in files)):
        return None
    all_changes = {}
    file_changes = {}
    for row in files:
        changes = patch_changes(api.contents(row['filename'], pr['base']['sha']),
                                api.contents(row['filename'], pr['head']['sha']))
        if changes is None:
            return None
        file_changes[row['filename']] = changes
        for name, versions in changes.items():
            if name in all_changes and all_changes[name] != versions:
                return None
            all_changes[name] = versions
    # Runtime and test locks must be updated together with identical versions.
    if file_changes['requirements.txt'] != file_changes['requirements-dev.txt']:
        return None
    # PR.base.sha names today's base ref, not necessarily an ancestor of the PR head.
    comparison = api.request(f"/compare/{main_sha}...{pr['head']['sha']}")
    if (comparison.get('merge_base_commit', {}).get('sha') != main_sha
            or comparison.get('behind_by') != 0 or comparison.get('status') != 'ahead'):
        return None
    return all_changes if head_checks_ready(api, pr['head']['sha']) else None


def request_post_merge_checks(api, number, head_sha, merge_sha):
    workflows = {
        'image.yml': {'expected_revision': merge_sha, 'build_image': True,
                      'full_validation': True, 'publish_image': False,
                      'installation_tags': False, 'anonymous_installation': False},
        'codeql.yml': {'expected_revision': merge_sha},
    }
    requested, failures = [], []
    for workflow, inputs in workflows.items():
        try:
            api.request('/actions/workflows/' + workflow + '/dispatches', method='POST',
                        data={'ref': 'main', 'inputs': inputs})
        except Exception as error:
            # A failed dispatch must not hide the real merge or prevent the independent check.
            failures.append(f'{workflow}: {type(error).__name__}: {error}')
        else:
            requested.append(workflow)
    if failures:
        raise RuntimeError(f'PR #{number}, Head {head_sha}, Merge {merge_sha}: Übernahme bestätigt; '
                           'Nachprüfung nicht vollständig angefordert: ' + '; '.join(failures))
    return requested


def run(api, dry_run=True):
    outcomes = []
    for item in api.pages('/pulls?state=open&base=main'):
        number = int(item['number'])
        pr = api.request(f'/pulls/{number}')
        main_sha = api.request('/git/ref/heads/main')['object']['sha']
        changes = evaluate(api, pr, main_sha)
        if not changes:
            outcomes.append({'number': number, 'result': 'Keine automatische Übernahme'})
            continue
        # A rerun on the same head can invalidate an earlier successful result.
        if not head_checks_ready(api, pr['head']['sha']):
            outcomes.append({'number': number, 'result': 'Prüfungen zwischenzeitlich geändert'})
            continue
        # Recheck both immutable identities immediately before the guarded merge request.
        current = api.request(f'/pulls/{number}')
        current_main = api.request('/git/ref/heads/main')['object']['sha']
        if (current_main != main_sha or not trusted_pr(current, current_main)
                or current['head']['sha'] != pr['head']['sha']):
            outcomes.append({'number': number, 'result': 'Stand zwischenzeitlich geändert'})
            continue
        if dry_run:
            outcomes.append({'number': number, 'result': 'Patchupdate freigabefähig', 'changes': changes})
            continue
        result = api.request(f'/pulls/{number}/merge', method='PUT', data={
            'sha': pr['head']['sha'], 'merge_method': 'squash',
            'commit_title': f'Python-Pakete aktualisieren (#{number})',
            'commit_message': 'Patch-Versionen nach erfolgreichen automatisierten Prüfungen übernommen.'})
        if not result.get('merged') or not re.fullmatch(r'[0-9a-f]{40}', result.get('sha', '')):
            raise RuntimeError('GitHub hat die Übernahme nicht bestätigt')
        # GITHUB_TOKEN merges do not trigger push workflows; request explicit, SHA-bound checks.
        requested = request_post_merge_checks(api, number, pr['head']['sha'], result['sha'])
        outcomes.append({'number': number, 'result': 'Patchupdate übernommen',
                         'head_sha': pr['head']['sha'], 'sha': result['sha'],
                         'post_merge_checks': {'state': 'angefordert, noch nicht bestätigt',
                                               'workflows': requested}})
    return outcomes


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--merge', action='store_true')
    args = parser.parse_args()
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise SystemExit('Falsches Repository; keine Übernahme')
    print(json.dumps(run(GitHub(os.environ['GH_TOKEN']), dry_run=not args.merge), ensure_ascii=False))

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


def checks_ready(checks, statuses):
    guards = [row for row in checks if row['name'].startswith('guard (')]
    names = {row['name']: row for row in checks}
    if len(guards) != 8 or any(row.get('conclusion') != 'success' or
                              row.get('app', {}).get('id') != 15368 for row in guards):
        return False
    for name, app in [('tests', 15368), ('analyze (python)', 15368),
                      ('analyze (javascript-typescript)', 15368), ('CodeQL', 57789)]:
        row = names.get(name, {})
        if row.get('conclusion') != 'success' or row.get('app', {}).get('id') != app:
            return False
    if any(row.get('status') != 'completed' or row.get('conclusion') not in
           {'success', 'skipped', 'neutral'} for row in checks):
        return False
    return not statuses.get('total_count') or statuses.get('state') == 'success'


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
            return json.load(response)

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
    if not files or any(row['filename'] not in FILES or row['status'] != 'modified' for row in files):
        return None
    all_changes = {}
    for row in files:
        changes = patch_changes(api.contents(row['filename'], pr['base']['sha']),
                                api.contents(row['filename'], pr['head']['sha']))
        if changes is None:
            return None
        for name, versions in changes.items():
            if name in all_changes and all_changes[name] != versions:
                return None
            all_changes[name] = versions
    # Runtime and test locks must be updated together with identical versions.
    if {row['filename'] for row in files} != FILES:
        return None
    old_runtime = api.contents('requirements.txt', pr['base']['sha'])
    new_runtime = api.contents('requirements.txt', pr['head']['sha'])
    old_dev = api.contents('requirements-dev.txt', pr['base']['sha'])
    new_dev = api.contents('requirements-dev.txt', pr['head']['sha'])
    if patch_changes(old_runtime, new_runtime) != patch_changes(old_dev, new_dev):
        return None
    checks = api.pages(f"/commits/{pr['head']['sha']}/check-runs?filter=latest", key='check_runs')
    statuses = api.request(f"/commits/{pr['head']['sha']}/status")
    return all_changes if checks_ready(checks, statuses) else None


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
        # Recheck both immutable identities immediately before the guarded merge request.
        current = api.request(f'/pulls/{number}')
        current_main = api.request('/git/ref/heads/main')['object']['sha']
        if not trusted_pr(current, current_main) or current['head']['sha'] != pr['head']['sha']:
            outcomes.append({'number': number, 'result': 'Stand zwischenzeitlich geändert'})
            continue
        if dry_run:
            outcomes.append({'number': number, 'result': 'Patchupdate freigabefähig', 'changes': changes})
            continue
        result = api.request(f'/pulls/{number}/merge', method='PUT', data={
            'sha': pr['head']['sha'], 'merge_method': 'squash',
            'commit_title': f'Python-Pakete aktualisieren (#{number})',
            'commit_message': 'Patch-Versionen nach erfolgreichen automatisierten Prüfungen übernommen.'})
        if not result.get('merged'):
            raise RuntimeError('GitHub hat die Übernahme nicht bestätigt')
        outcomes.append({'number': number, 'result': 'Patchupdate übernommen', 'sha': result['sha']})
    return outcomes


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--merge', action='store_true')
    args = parser.parse_args()
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise SystemExit('Falsches Repository; keine Übernahme')
    print(json.dumps(run(GitHub(os.environ['GH_TOKEN']), dry_run=not args.merge), ensure_ascii=False))

"""Select documentation checks only after a fully checked initial commit."""
import os
from pathlib import Path
import subprocess


def bounded_paths(paths):
    return all(path.startswith(('docs/', 'tests/', '.github/')) or path in {
        'README.md', 'CHANGELOG.md', '.gitignore', '.gitattributes'
    } for path in paths)


def targeted():
    if os.environ.get('MCJ_FULL_VALIDATION') == 'true':
        return False
    try:
        roots = subprocess.check_output(
            ['git', 'rev-list', '--max-parents=0', 'HEAD'], text=True).splitlines()
        if len(roots) != 1:
            return False
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        if head == roots[0]:
            return False
        paths = subprocess.check_output(
            ['git', 'diff', '--name-only', roots[0], 'HEAD'], text=True).splitlines()
        return bounded_paths(paths)
    except subprocess.CalledProcessError:
        return False


if __name__ == '__main__':
    result = 'true' if targeted() else 'false'
    print('Gezielte Dokumentations- und Paketprüfung: ' + result)
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with Path(output).open('a', encoding='utf-8') as stream:
            stream.write('targeted=' + result + '\n')

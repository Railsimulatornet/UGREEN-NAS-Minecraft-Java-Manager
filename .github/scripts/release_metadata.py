"""Read release metadata without importing application dependencies."""
import ast
from datetime import datetime, timezone
import os
from pathlib import Path
import re


def version(root):
    tree = ast.parse((root / 'mcj/__init__.py').read_text(encoding='utf-8'))
    values = [node.value.value for node in tree.body
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == '__version__'
                      for target in node.targets)
              and isinstance(node.value, ast.Constant)
              and isinstance(node.value.value, str)]
    if len(values) != 1 or not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', values[0]):
        raise ValueError('Die Projektversion muss eine eindeutige Versionsnummer wie 1.0.0 sein.')
    return values[0]


def tags(app_version, revision, source_ref, installation=False):
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Der vollständige Quell-Commit fehlt.')
    tagged = source_ref.startswith('refs/tags/')
    if tagged and source_ref != 'refs/tags/v' + app_version:
        raise ValueError('Versions-Tag und Projektversion stimmen nicht überein.')
    if installation and source_ref != 'refs/heads/main' and not tagged:
        raise ValueError('Installationsversion und stable benötigen main oder den passenden Versions-Tag.')
    result = ['sha-' + revision]
    if installation or tagged:
        result.extend([app_version, 'stable'])
    elif source_ref == 'refs/heads/main':
        result.append('edge')
    return result


def main():
    root = Path(__file__).resolve().parents[2]
    app_version = version(root)
    image_tags = tags(app_version, os.environ['SOURCE_REVISION'], os.environ['SOURCE_REF'],
                      os.environ.get('INSTALLATION_TAGS') == 'true')
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with Path(output).open('a', encoding='utf-8') as stream:
            stream.write('version=' + app_version + '\n')
            stream.write('tags=' + ','.join(image_tags) + '\n')
            stream.write('created=' + datetime.now(timezone.utc).isoformat() + '\n')
    print('Projektversion: ' + app_version)
    print('Vorgesehene Image-Tags: ' + ', '.join(image_tags))


if __name__ == '__main__':
    main()

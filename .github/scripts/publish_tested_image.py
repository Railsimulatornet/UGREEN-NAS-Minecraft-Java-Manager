"""Transfer the loaded, tested image without rebuilding or replacing version tags."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'railsimulatornet/ugreen-nas-minecraft-java-manager'
ACCEPT = 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'


def allowed_tags(version, revision, tags):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Ungültige Veröffentlichungsidentität')
    expected = ['sha-' + revision, version, 'stable']
    if tags != expected:
        raise ValueError('Die Veröffentlichung benötigt genau Commit, Versionsnummer und stable')
    return expected


def manifest_config(manifest):
    if 'manifests' in manifest or not re.fullmatch(r'sha256:[0-9a-f]{64}', manifest.get('config', {}).get('digest', '')):
        raise ValueError('Unerwarteter Image-Index oder fehlende Image-Konfiguration')
    return manifest['config']['digest']


def main():
    version = os.environ['EXPECTED_VERSION']; revision = os.environ['EXPECTED_REVISION']
    tags = allowed_tags(version, revision, os.environ['RELEASE_TAGS'].split(','))
    info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'mcj-candidate:ci'], text=True))[0]
    labels = info['Config']['Labels']
    assert labels['org.opencontainers.image.version'] == version
    assert labels['org.opencontainers.image.revision'] == revision
    assert info['Os'] == 'linux' and info['Architecture'] == 'amd64'
    credential = base64.b64encode((os.environ['REGISTRY_USERNAME'] + ':' + os.environ['REGISTRY_TOKEN']).encode()).decode()
    url = 'https://auth.docker.io/token?' + urllib.parse.urlencode({
        'service': 'registry.docker.io', 'scope': 'repository:' + REPOSITORY + ':pull'})
    with urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': 'Basic ' + credential}), timeout=30) as response:
        token = json.load(response)['token']

    def manifest(tag):
        request = urllib.request.Request('https://registry-1.docker.io/v2/' + REPOSITORY + '/manifests/' + tag,
            headers={'Authorization': 'Bearer ' + token, 'Accept': ACCEPT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                import hashlib
                raw = response.read(4 * 1024 * 1024 + 1)
                assert len(raw) <= 4 * 1024 * 1024
                digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
                assert response.headers['Docker-Content-Digest'] == digest
                return digest, json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    # Validate every immutable tag before changing any tag.
    for tag in tags[:-1]:
        existing = manifest(tag)
        if existing and manifest_config(existing[1]) != info['Id']:
            raise RuntimeError('Ein veröffentlichter Versions- oder Commit-Tag darf nicht ersetzt werden: ' + tag)
    results = []
    for tag in tags:
        reference = REPOSITORY + ':' + tag
        subprocess.run(['docker', 'tag', info['Id'], reference], check=True)
        subprocess.run(['docker', 'push', reference], check=True)
        digest, value = manifest(tag)
        assert manifest_config(value) == info['Id']
        results.append({'tag': tag, 'digest': digest, 'image_id': info['Id']})
    assert len({x['digest'] for x in results}) == 1
    report = {'version': version, 'revision': revision, 'platform': 'linux/amd64',
              'image_id': info['Id'], 'created': labels['org.opencontainers.image.created'],
              'tags': results, 'tested_image_rebuilt': False}
    Path('/tmp/release-image.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

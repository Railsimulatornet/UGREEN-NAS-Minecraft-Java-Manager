"""Read registry tags and image identities without pulling, pushing or deleting images."""
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'railsimulatornet/ugreen-nas-minecraft-java-manager'
REGISTRY = 'https://registry-1.docker.io'
MEDIA = ', '.join(['application/vnd.oci.image.index.v1+json', 'application/vnd.docker.distribution.manifest.list.v2+json',
                   'application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json'])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, headers):
    with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, headers=headers), timeout=30) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('Registry response exceeds metadata limit')
        return json.loads(raw), response.headers, raw


def main():
    basic = base64.b64encode((os.environ['REGISTRY_USERNAME'] + ':' + os.environ['REGISTRY_TOKEN']).encode()).decode()
    query = urllib.parse.urlencode({'service': 'registry.docker.io', 'scope': 'repository:' + REPOSITORY + ':pull'})
    auth, _, _ = request('https://auth.docker.io/token?' + query, {'Authorization': 'Basic ' + basic})
    headers = {'Authorization': 'Bearer ' + auth['token'], 'Accept': MEDIA}
    prefix = '/v2/' + REPOSITORY
    url = REGISTRY + prefix + '/tags/list?n=100'
    tags = set()
    pages = set()
    while url:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'registry-1.docker.io' or parsed.path != prefix + '/tags/list' or url in pages:
            raise ValueError('Unexpected registry pagination')
        pages.add(url)
        data, meta, _ = request(url, headers)
        tags.update(data.get('tags') or [])
        if len(tags) > 1000:
            raise ValueError('Inventory exceeds 1000 tags')
        link = meta.get('Link', '')
        match = re.fullmatch(r'<([^>]+)>;\s*rel="next"', link) if link else None
        if link and not match:
            raise ValueError('Unexpected registry pagination header')
        url = urllib.parse.urljoin(REGISTRY, match[1]) if match else None
    records = []
    for tag in sorted(tags):
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', tag):
            raise ValueError('Invalid image tag')
        manifest, meta, raw = request(REGISTRY + prefix + '/manifests/' + tag, headers)
        digest = meta.get('Docker-Content-Digest', '')
        if digest != 'sha256:' + hashlib.sha256(raw).hexdigest():
            raise ValueError('Manifest digest mismatch')
        platforms = []
        if 'manifests' in manifest:
            platforms = [item.get('platform', {}) for item in manifest['manifests']]
            selected = [item for item in manifest['manifests'] if item.get('platform', {}).get('os') == 'linux' and item.get('platform', {}).get('architecture') == 'amd64']
            if len(selected) != 1:
                raise ValueError('Expected one linux/amd64 manifest')
            child = selected[0]['digest']
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', child):
                raise ValueError('Invalid child manifest digest')
            manifest, _, raw = request(REGISTRY + prefix + '/manifests/' + child, headers)
            if child != 'sha256:' + hashlib.sha256(raw).hexdigest():
                raise ValueError('Child manifest digest mismatch')
        config_id = manifest['config']['digest']
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', config_id):
            raise ValueError('Invalid image configuration digest')
        # Config blobs can redirect to an authenticated CDN. Obtain only the manifest
        # identity here; do not forward registry credentials to another host.
        records.append({'tag': tag, 'registry_digest': digest, 'image_config_id': config_id, 'platforms': platforms})
    report = {'repository': REPOSITORY, 'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'authenticated_read': True, 'images_pulled': False, 'images_pushed': False, 'images_deleted': False,
              'tags': records, 'tag_count': len(records)}
    Path('/tmp/registry-inventory.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Registry-Tags erfasst: ' + str(len(records)) + '. Keine Images übertragen oder gelöscht.')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit('Registry-Inventar fehlgeschlagen: HTTP ' + str(error.code))

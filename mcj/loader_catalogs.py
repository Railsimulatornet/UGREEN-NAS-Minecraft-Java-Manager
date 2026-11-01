"""Official Forge and legacy NeoForge identities, bounded by installer metadata."""
import hashlib
import io
import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile

import httpx

from . import mods
from .http_identity import AGENT

ORIGINS = {
    'FORGE': ('https://maven.minecraftforge.net/', 'net.minecraftforge'),
    'NEOFORGE': ('https://maven.neoforged.net/releases/', 'net.neoforged'),
}
METADATA_LIMIT = 2 * 1024 ** 2
INSTALLER_LIMIT = 32 * 1024 ** 2


def legacy_neoforge(configuration):
    return configuration.get('loader') == 'NEOFORGE' and configuration.get('version') == '1.20.1'


def mod_format(configuration):
    # The 1.20.1 NeoForge fork still declares the Forge mod id and TOML format.
    # This exception never applies to later NeoForge releases.
    return 'FORGE' if legacy_neoforge(configuration) else configuration['loader']


def identity(loader, minecraft, version=None):
    if loader not in ORIGINS or not isinstance(minecraft, str) or not re.fullmatch(r'\d+(?:\.\d+){1,2}', minecraft):
        raise ValueError('loader_metadata_identity_invalid')
    if loader == 'NEOFORGE' and minecraft != '1.20.1':
        raise ValueError('loader_metadata_identity_invalid')
    if version is not None and (not isinstance(version, str) or not re.fullmatch(r'\d+(?:\.\d+){2,3}', version)):
        raise ValueError('stable_loader_unverified')
    origin, group = ORIGINS[loader]
    base = group.replace('.', '/') + '/forge/'
    if version is None:
        return origin + base + 'maven-metadata.xml'
    coordinate = minecraft + '-' + version
    artifact = base + coordinate + '/forge-' + coordinate
    return {
        'key': loader + ':' + minecraft + ':' + version,
        'id': minecraft + '-forge-' + version,
        'coordinate': group + ':forge:' + coordinate + ':universal',
        'installer': origin + artifact + '-installer.jar',
        'source': origin + artifact + '-universal.jar',
        'library_path': artifact + '-universal.jar',
    }


def fetch(client, url, limit):
    raw = bytearray()
    with client.stream('GET', url, follow_redirects=False) as response:
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError('loader_metadata_source_invalid')
        for block in response.iter_bytes(65536):
            raw.extend(block)
            if len(raw) > limit:
                raise ValueError('loader_metadata_limit')
    return bytes(raw)


class CatalogTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError('version_metadata_limit')


def available(client, loader, minecraft):
    raw = fetch(client, identity(loader, minecraft), METADATA_LIMIT)
    try:
        tree = ET.fromstring(raw, parser=ET.XMLParser(target=CatalogTreeBuilder()))
    except ET.ParseError:
        raise ValueError('loader_metadata_identity_invalid') from None
    if tree.findtext('groupId') != ORIGINS[loader][1] or tree.findtext('artifactId') != 'forge':
        raise ValueError('loader_metadata_identity_invalid')
    prefix = minecraft + '-'
    values = {item.text[len(prefix):] for item in tree.findall('./versioning/versions/version')
              if item.text and item.text.startswith(prefix) and re.fullmatch(r'\d+(?:\.\d+){2,3}', item.text[len(prefix):])}
    return sorted(values, key=lambda value: tuple(map(int, value.split('.'))), reverse=True)


def installer_proof(raw, expected, minecraft):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            documents = []
            names = archive.namelist()
            for name in ('install_profile.json', 'version.json'):
                if names.count(name) != 1:
                    raise ValueError('loader_metadata_identity_invalid')
                member = archive.getinfo(name)
                if member.file_size > METADATA_LIMIT:
                    raise ValueError('loader_metadata_limit')
                documents.append(json.loads(archive.read(member)))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeError):
        raise ValueError('loader_metadata_identity_invalid') from None
    profile, version = documents
    if (profile.get('minecraft') != minecraft or profile.get('version') != expected['id']
            or version.get('id') != expected['id'] or version.get('inheritsFrom') != minecraft):
        raise ValueError('loader_metadata_identity_invalid')
    libraries = []
    for document in documents:
        for library in document.get('libraries', []):
            if library.get('name') == expected['coordinate']:
                libraries.append(library.get('downloads', {}).get('artifact', {}))
    if not libraries or any(item != libraries[0] for item in libraries):
        raise ValueError('loader_metadata_identity_invalid')
    proof = libraries[0]
    if (proof.get('url') != expected['source'] or proof.get('path') != expected['library_path']
            or not re.fullmatch('[0-9a-f]{40}', str(proof.get('sha1', '')))
            or type(proof.get('size')) is not int or not 0 < proof['size'] <= mods.MAX_JAR):
        raise ValueError('loader_metadata_identity_invalid')
    return proof


def ensure_components(store, loader, minecraft, version, client=None):
    expected = identity(loader, minecraft, version)
    catalog = store.get('loader_components') or {}
    cached = catalog.get(expected['key']) or {}
    path = store.state / 'loader-cache' / (loader.lower() + '-' + minecraft + '-' + version + '.jar')
    if path.parent.resolve() != path.parent.absolute() or path.is_symlink():
        raise ValueError('loader_runtime_hash_mismatch')
    matches = all(cached.get(key) == value for key, value in {
        'loader': loader, 'minecraft': minecraft, 'loader_version': version,
        'source': expected['source'], 'library_path': expected['library_path'],
    }.items())
    if (matches and path.is_file() and path.stat().st_size <= mods.MAX_JAR
            and re.fullmatch('[0-9a-f]{64}', str(cached.get('sha256', '')))
            and hashlib.sha256(path.read_bytes()).hexdigest() == cached['sha256']):
        return cached

    def acquire(provider):
        installer = fetch(provider, expected['installer'], INSTALLER_LIMIT)
        proof = installer_proof(installer, expected, minecraft)
        raw = fetch(provider, expected['source'], mods.MAX_JAR)
        if len(raw) != proof['size'] or hashlib.sha1(raw).hexdigest() != proof['sha1']:
            raise ValueError('loader_metadata_hash_mismatch')
        metadata = mods.inspect_jar(raw, preferred_loader='FORGE')
        if (metadata['loader'] != 'FORGE' or len(metadata['mods']) != 1
                or metadata['mods'][0]['id'] != 'forge'
                or metadata['mods'][0]['version'] not in (version, '${global.forgeVersion}')):
            raise ValueError('loader_metadata_identity_invalid')
        result = {
            'loader': loader, 'minecraft': minecraft, 'loader_version': version,
            'source': expected['source'], 'library_path': expected['library_path'],
            'sha256': hashlib.sha256(raw).hexdigest(),
            'installer_sha256': hashlib.sha256(installer).hexdigest(),
            'components': {'forge': version}, 'checked': time.time(),
            'integrity': 'official_https_installer_and_universal; actual runtime loader hash must match',
        }
        store.atomic(path, raw, 0o440)
        catalog[expected['key']] = result
        store.set('loader_components', catalog)
        return result

    if client is not None:
        return acquire(client)
    with httpx.Client(timeout=25, follow_redirects=False, headers={'User-Agent': AGENT}) as provider:
        return acquire(provider)


def verify_runtime(data, configuration):
    """Reconstruct the library location; a saved proof cannot choose a file path."""
    expected = identity(configuration['loader'], configuration['version'], configuration['loader_version'])
    proof = configuration.get('loader_components') or {}
    path = data / 'libraries' / expected['library_path']
    if (proof.get('loader') != configuration['loader']
            or proof.get('minecraft') != configuration['version']
            or proof.get('loader_version') != configuration['loader_version']
            or path.resolve() != path.absolute() or not path.is_file()
            or path.stat().st_size > mods.MAX_JAR
            or hashlib.sha256(path.read_bytes()).hexdigest() != proof.get('sha256')):
        raise ValueError('loader_runtime_hash_mismatch')

"""Use the already installed legacy NeoForge runtime without Maven discovery."""
from . import loader_catalogs


def start_script(data,configuration,script):
    if not loader_catalogs.legacy_neoforge(configuration):
        return script
    loader_catalogs.verify_runtime(data,configuration)
    launcher=data/'run.sh'
    if (launcher.resolve()!=launcher.absolute() or not launcher.is_file()
            or not 0<launcher.stat().st_size<=65536):
        raise ValueError('isolated_runtime_launcher_invalid')
    # The pinned Java17 image resolves legacy NeoForge through Maven even when
    # its exact version is installed. CUSTOM keeps the image's normal startup
    # and memory setup while launching this extracted installation offline.
    normalized=script.replace(b'\r\n',b'\n')
    if not normalized.endswith(b'exec /start\n'):
        raise ValueError('isolated_runtime_start_script_invalid')
    return normalized[:-len(b'exec /start\n')]+(
        b'export TYPE=CUSTOM\nexport CUSTOM_SERVER=/data/run.sh\n'
        b'export FAMILY=FORGE\nexec /start\n')

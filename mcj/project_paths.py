"""Explicit storage layout; changing code alone never moves existing data."""
import os
from pathlib import Path,PurePosixPath

SERVICE_PATHS={
    'source':'manager/source','state':'manager/state','staging':'manager/staging','secrets':'manager/secrets',
    'server':'mcj_minecraft/data','mods':'mcj_minecraft/mods','disabled':'mcj_minecraft/disabled',
    'control':'mcj_controller/control','releases':'mcj_controller/releases',
    '.rollback':'mcj_controller/.rollback','.restore-tests':'mcj_controller/.restore-tests',
    '.acceptance':'mcj_controller/.acceptance','.install':'mcj_controller/.install',
}


def project_path(root,relative,layout=None):
    layout=os.environ.get('MCJ_LAYOUT','legacy') if layout is None else layout
    if layout not in {'legacy','services-v1'}:raise ValueError('unknown_project_layout')
    value=str(relative)
    path=PurePosixPath(value)
    if not value or '\\' in value or ':' in value or path.is_absolute() or '..' in path.parts:
        raise ValueError('unsafe_project_path')
    if layout=='services-v1' and path.parts and path.parts[0] in SERVICE_PATHS:
        path=PurePosixPath(SERVICE_PATHS[path.parts[0]]).joinpath(*path.parts[1:])
    return Path(root).joinpath(*path.parts)

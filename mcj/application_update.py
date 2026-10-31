"""Read-only update information. Privileged updating runs only from UGOS."""
import json,os,stat
from pathlib import Path
from . import __version__

PHASES={'checking','backup','updating','health','complete','failed','rolled_back'}

def status(store):
    result={'version':__version__,'phase':'ready','progress':0}
    path=store.state/'application-update.json'
    try:
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>8192:return {**result,'phase':'unavailable'}
            value=json.loads(stream.read(8193))
        if value.get('phase') not in PHASES or type(value.get('progress')) is not int or not 0<=value['progress']<=100:return {**result,'phase':'unavailable'}
        result.update(phase=value['phase'],progress=value['progress'])
        for key in ('credentials_preserved','game_unchanged','services_healthy','rolled_back'):
            if type(value.get(key)) is bool:result[key]=value[key]
    except FileNotFoundError:pass
    except (OSError,ValueError,TypeError,AttributeError):result['phase']='unavailable'
    return result

def template():
    return (Path(__file__).resolve().parents[1]/'deploy/ugos-aktualisierung.yaml').read_text(encoding='utf-8')

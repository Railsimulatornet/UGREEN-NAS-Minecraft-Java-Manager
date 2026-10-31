"""Exact, opt-in client companion; never part of the dedicated server mod set."""
from pathlib import Path
import hashlib

SHA256='bbee136fdea190e5cb1a31c3ed6f93616c1ea12210a6ec4572f4a6e047a0c304'
FILENAME='mcj-create-train-fix-1.0.4-neoforge-26.3.jar'
RUNTIME={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.99'}
CREATE_HASHES={'4e8684618edeedae5dbfbe5ec8ba05d57c8c251cb34beb69160f53cbd97b4099',
               '9008cd82a9233fdb0ddadb33cd5fb11c9fc26b9ea102ad245319a9aa1b2964c8'}


def bundle(graphics,active,selected,report,bundled):
    from . import client_packs as cp,mods
    approved=(graphics or {}).get('train_compatibility_patch')
    if approved is None:return
    if approved!=SHA256 or active!=RUNTIME:raise ValueError('client_create_patch_unverified')
    create=[r for r in selected if any(m['id']=='create' for m in r['metadata']['mods'])]
    if len(create)!=1 or create[0]['hashes']['sha256'] not in CREATE_HASHES:
        raise ValueError('client_create_patch_unverified')
    if any(any(m['id']=='mcj_create_train_fix' for m in r['metadata']['mods']) for r in selected):
        raise ValueError('client_graphics_duplicate')
    folder=Path(__file__).parent/'client_pack_resources'
    raw=cp.read_bounded(folder/FILENAME,mods.MAX_JAR)
    if hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('client_create_patch_unverified')
    metadata=mods.inspect_jar(raw)
    if metadata['mods']!=[{'id':'mcj_create_train_fix','name':'Create Train Client Position Compatibility','version':'1.0.4'}]:
        raise ValueError('client_create_patch_unverified')
    selected.append({'filename':FILENAME,'hashes':cp.hashes(raw),'size':len(raw),
                     'metadata':metadata,'source':'mcj_client_companion','origin':{}})
    report.append({'filename':FILENAME,'mods':metadata['mods'],'sha256':SHA256,
        'client':'required','license':'MIT','embedded_client_companion':True,
        'note':'Client-only Create seated-train position correction 1.0.4; exact runtime and Create hashes checked.'})
    bundled['overrides/mods/'+FILENAME]=raw
    for name in ['Create-Train-Fix-1.0.4-LICENSE.txt','Create-Train-Fix-1.0.4-NOTICE.txt']:
        bundled['overrides/MCJ-LICENSES/'+name]=cp.read_bounded(folder/name,65536)

"""Checksum-pinned client companions; never part of the dedicated server mod set."""
from pathlib import Path
import hashlib

SHA256='9838dacd19718317b982c8ebad7e8ed67435b82e3eccb74ef4cdf70095977565'
FILENAME='mcj-create-train-fix-1.0.5-neoforge-26.3.jar'
RUNTIME={'version':'26.3','java':25,'loader':'NEOFORGE','loader_version':'26.3.0.99'}
CREATE_HASHES={'4e8684618edeedae5dbfbe5ec8ba05d57c8c251cb34beb69160f53cbd97b4099',
               '9008cd82a9233fdb0ddadb33cd5fb11c9fc26b9ea102ad245319a9aa1b2964c8'}
ARTIFACTS={
    '5fc908d9edcf62d45cbe44486715711b17426deb51908aba053f0fb4b8ec3e55':
        ('1.0.4','mcj-create-train-fix-1.0.4-neoforge-26.3.jar'),
    SHA256:('1.0.5',FILENAME),
}


def bundle(graphics,active,selected,report,bundled):
    from . import client_packs as cp,mods
    approved=(graphics or {}).get('train_compatibility_patch')
    if approved is None:return
    if not isinstance(approved,str) or approved not in ARTIFACTS or active!=RUNTIME:
        raise ValueError('client_create_patch_unverified')
    version,filename=ARTIFACTS[approved]
    create=[r for r in selected if any(m['id']=='create' for m in r['metadata']['mods'])]
    if len(create)!=1 or create[0]['hashes']['sha256'] not in CREATE_HASHES:
        raise ValueError('client_create_patch_unverified')
    if any(any(m['id']=='mcj_create_train_fix' for m in r['metadata']['mods']) for r in selected):
        raise ValueError('client_graphics_duplicate')
    folder=Path(__file__).parent/'client_pack_resources'
    raw=cp.read_bounded(folder/filename,mods.MAX_JAR)
    if hashlib.sha256(raw).hexdigest()!=approved:raise ValueError('client_create_patch_unverified')
    metadata=mods.inspect_jar(raw)
    if metadata['mods']!=[{'id':'mcj_create_train_fix','name':'Create Train Client Position Compatibility','version':version}]:
        raise ValueError('client_create_patch_unverified')
    license_name='Create-Train-Fix-'+version+'-LICENSE.txt'
    notice_name='Create-Train-Fix-'+version+'-NOTICE.txt'
    notices={name:cp.read_bounded(folder/name,65536) for name in [license_name,notice_name]}
    selected.append({'filename':filename,'hashes':cp.hashes(raw),'size':len(raw),
                     'metadata':metadata,'source':'mcj_client_companion','origin':{}})
    scope='passengers and observers' if version=='1.0.5' else 'seated passengers'
    report.append({'filename':filename,'mods':metadata['mods'],'sha256':approved,
        'client':'required','license':'MIT','embedded_client_companion':True,
        'note':'Client-only Create train position correction '+version+' for '+scope+'; exact runtime and Create files checked.'})
    bundled['overrides/mods/'+filename]=raw
    for name,value in notices.items():bundled['overrides/MCJ-LICENSES/'+name]=value

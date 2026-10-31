"""Build the client-only Create position-sync correction from cached, matching NeoForge libraries."""
import argparse,hashlib,json,os,subprocess,zipfile
from pathlib import Path

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--libraries',type=Path,required=True)
parser.add_argument('--jdk',type=Path,required=True)
parser.add_argument('--create',type=Path,required=True)
parser.add_argument('--annotations',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args()
libs=args.libraries.resolve();output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
create=args.create.resolve()
supported_create=('4e8684618edeedae5dbfbe5ec8ba05d57c8c251cb34beb69160f53cbd97b4099',
    '9008cd82a9233fdb0ddadb33cd5fb11c9fc26b9ea102ad245319a9aa1b2964c8')
assert hashlib.sha256(create.read_bytes()).hexdigest() in supported_create
priority=[create,libs/'net/neoforged/minecraft-client-patched/26.3.0.99/minecraft-client-patched-26.3.0.99.jar',
    libs/'net/neoforged/neoforge/26.3.0.99/neoforge-26.3.0.99-universal.jar',
    libs/'net/neoforged/fancymodloader/loader/12.0.12/loader-12.0.12.jar',
    libs/'net/neoforged/bus/8.0.5/bus-8.0.5.jar',
    libs/'net/fabricmc/sponge-mixin/0.17.4+mixin.0.8.7/sponge-mixin-0.17.4+mixin.0.8.7.jar']
assert all(p.is_file() for p in priority)
compile_only=output/'compile-only';compile_only.mkdir(exist_ok=True)
with zipfile.ZipFile(create) as original_create:
    for member in original_create.namelist():
        if member.startswith('META-INF/jarjar/') and member.endswith('.jar'):
            dependency=compile_only/member.rsplit('/',1)[-1]
            dependency.write_bytes(original_create.read(member));priority.append(dependency)
with zipfile.ZipFile(priority[2]) as neoforge:
    mixinextras=compile_only/'mixinextras-neoforge-0.5.5.jar'
    mixinextras.write_bytes(neoforge.read('META-INF/jarjar/mixinextras-neoforge-0.5.5.jar'))
assert args.annotations.is_file()
priority.extend([mixinextras,args.annotations.resolve()])
priority.extend(p for p in sorted(libs.rglob('*.jar')) if p not in priority)
sources=sorted(root.glob('*.java'))
classes=output/'classes';classes.mkdir(exist_ok=True)
arguments=['-encoding','UTF-8','-proc:none','-cp',os.pathsep.join(str(p).replace('\\','/') for p in priority),
    '-d',str(classes),*[str(p) for p in sources]]
argument_file=output/'javac.args'
argument_file.write_text('\n'.join('"'+x.replace('\\','/')+'"' for x in arguments),encoding='utf-8')
javac=args.jdk/'bin'/('javac.exe' if os.name=='nt' else 'javac')
result=subprocess.run([str(javac),'@'+str(argument_file)],capture_output=True,text=True)
(output/'build.log').write_text(result.stdout+result.stderr,encoding='utf-8')
if result.returncode:raise RuntimeError(result.stderr[-4000:])
metadata='''modLoader="javafml"
loaderVersion="[12,)"
license="MIT"
[[mods]]
modId="mcj_create_train_fix"
version="1.0.4"
displayName="Create Train Client Position Compatibility"
description="Preserves Create interpolation for a seated passenger during ordinary entity position syncs."
displayTest="IGNORE_ALL_VERSION"
[[mixins]]
config="mcj-create-trains.mixins.json"
[[dependencies.mcj_create_train_fix]]
modId="minecraft"
type="required"
versionRange="[26.3]"
side="CLIENT"
[[dependencies.mcj_create_train_fix]]
modId="neoforge"
type="required"
versionRange="[26.3.0.99]"
side="CLIENT"
[[dependencies.mcj_create_train_fix]]
modId="create"
type="required"
versionRange="[6.0.11-adapted-1.31]"
ordering="AFTER"
side="CLIENT"
'''
config={'required':True,'minVersion':'0.8.7','package':'de.romanglos.mcj.createtrains.mixin',
    'compatibilityLevel':'JAVA_25','client':['ClientTrainPositionMixin'],
    'injectors':{'defaultRequire':1}}
entries={'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\nFMLModType: MOD\r\nAutomatic-Module-Name: mcj_create_train_fix\r\n\r\n',
    'META-INF/neoforge.mods.toml':metadata.encode(),
    'mcj-create-trains.mixins.json':(json.dumps(config,indent=2)+'\n').encode(),
    'LICENSE':(root/'LICENSE').read_bytes(),'NOTICE':(root/'NOTICE').read_bytes()}
for p in sources:entries['META-INF/sources/'+p.name]=p.read_bytes()
for p in classes.rglob('*.class'):entries[p.relative_to(classes).as_posix()]=p.read_bytes()
jar=output/'mcj-create-train-fix-1.0.4-neoforge-26.3.jar'
with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for name,raw in sorted(entries.items()):
        info=zipfile.ZipInfo(name,date_time=(2026,10,31,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
        archive.writestr(info,raw)
proof={'file':jar.name,'bytes':jar.stat().st_size,'sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
    'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    'create_sha256':hashlib.sha256(create.read_bytes()).hexdigest(),
    'supported_create_sha256':list(supported_create),
    'minecraft_client_sha256':hashlib.sha256(priority[1].read_bytes()).hexdigest(),
    'client_only':True,'changes_server_or_guard':False,'original_create_unchanged':True,
    'runtime_tested':False,'live_installed':False,'reproducible_build':False}
(output/'build-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(json.dumps(proof,indent=2))

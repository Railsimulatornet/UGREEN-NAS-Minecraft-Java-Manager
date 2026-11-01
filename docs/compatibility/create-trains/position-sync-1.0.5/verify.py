"""Test the built gate, exact packet call sites, and the actual MC bytecode mechanism."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--baseline-jar',type=Path,required=True)
parser.add_argument('--first-build',type=Path,required=True)
parser.add_argument('--second-build',type=Path,required=True)
parser.add_argument('--libraries',type=Path,required=True)
parser.add_argument('--jdk',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args()
root=args.output_dir.resolve();root.mkdir(parents=True,exist_ok=True)
build=args.first_build.resolve()
proof=json.loads((build/'build-proof.json').read_text())
jar=build/proof['file']
assert jar.read_bytes()==(args.second_build.resolve()/jar.name).read_bytes()
jdk=args.jdk.resolve()/'bin'

def run(args):
    p=subprocess.run(args,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
    return p.stdout.strip()

fixture=root/'position-contract';fixture.mkdir(exist_ok=True)
sources={
'net/minecraft/world/phys/Vec3.java':'''package net.minecraft.world.phys; public record Vec3(double x,double y,double z) {
 public double distanceToSqr(Vec3 b){return Math.pow(x-b.x,2)+Math.pow(y-b.y,2)+Math.pow(z-b.z,2);}}''',
'net/minecraft/world/level/Level.java':'package net.minecraft.world.level; public class Level {public boolean client=true; public boolean isClientSide(){return client;}}',
'net/minecraft/world/entity/Entity.java':'''package net.minecraft.world.entity; public class Entity {
 public net.minecraft.world.level.Level world=new net.minecraft.world.level.Level(); public boolean removed;
 public net.minecraft.world.level.Level level(){return world;} public boolean isRemoved(){return removed;}
 public boolean isLocalInstanceAuthoritative(){return false;} public net.minecraft.world.phys.Vec3 position(){return new net.minecraft.world.phys.Vec3(0,0,0);}}''',
'net/minecraft/client/player/LocalPlayer.java':'''package net.minecraft.client.player; public class LocalPlayer extends net.minecraft.world.entity.Entity {
 public net.minecraft.world.entity.Entity vehicle;public boolean passenger=true;
 public boolean isPassenger(){return passenger;} public net.minecraft.world.entity.Entity getVehicle(){return vehicle;}}''',
'net/minecraft/client/Minecraft.java':'''package net.minecraft.client;public class Minecraft {
 private static final Minecraft INSTANCE=new Minecraft();public net.minecraft.client.player.LocalPlayer player;
 public static Minecraft getInstance(){return INSTANCE;}}''',
'net/minecraft/client/multiplayer/ClientPacketListener.java':'package net.minecraft.client.multiplayer; public class ClientPacketListener {}',
'net/minecraft/world/entity/PositionPath.java':'package net.minecraft.world.entity; public interface PositionPath {net.minecraft.world.phys.Vec3 endPosition();}',
'net/minecraft/network/protocol/game/ClientboundEntityPositionSyncPacket.java':'package net.minecraft.network.protocol.game; public record ClientboundEntityPositionSyncPacket(net.minecraft.world.entity.PositionPath position) {}',
'net/minecraft/network/protocol/game/ClientboundMoveEntityPacket.java':'package net.minecraft.network.protocol.game; public class ClientboundMoveEntityPacket {}',
'com/llamalad7/mixinextras/injector/wrapoperation/Operation.java':'package com.llamalad7.mixinextras.injector.wrapoperation; public interface Operation<T>{T call(Object... arguments);}',
'com/simibubi/create/content/trains/entity/Train.java':'package com.simibubi.create.content.trains.entity;public class Train {public boolean derailed;}',
'com/simibubi/create/content/trains/entity/Carriage.java':'package com.simibubi.create.content.trains.entity;public class Carriage {public Train train=new Train();}',
'com/simibubi/create/content/trains/entity/CarriageContraptionEntity.java':'''package com.simibubi.create.content.trains.entity;
 public class CarriageContraptionEntity extends net.minecraft.world.entity.Entity {
 public boolean validForRender=true,firstPositionUpdate;public Carriage carriage=new Carriage(); public Carriage getCarriage(){return carriage;}}''',
'org/slf4j/Logger.java':'package org.slf4j;public interface Logger {void info(String format,Object... values);}',
'org/slf4j/LoggerFactory.java':'''package org.slf4j;public class LoggerFactory {public static int lines;public static String lastRole;
 public static Logger getLogger(String n){return (f,v)->{if(!f.startsWith("[MCJ-TrainFix] sample="))throw new AssertionError();lastRole=String.valueOf(v[1]);lines++;};}}''',
'PositionContract.java':'''import de.romanglos.mcj.createtrains.TrainPositionSync;
import net.minecraft.client.Minecraft;import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;import net.minecraft.world.phys.Vec3;
import com.simibubi.create.content.trains.entity.CarriageContraptionEntity;
public class PositionContract {
 static int cases;
 static void expect(boolean v,boolean expected){cases++;if(v!=expected)throw new AssertionError("case "+cases);}
 public static void main(String[] ignored)throws Exception {
  var p=new LocalPlayer();var t=new CarriageContraptionEntity();p.vehicle=t;p.world=t.world;
  Minecraft.getInstance().player=p;
  expect(TrainPositionSync.eligible(p,t,null),true);
  expect(TrainPositionSync.eligible(null,t,null),false);
  expect(TrainPositionSync.eligible(p,new Entity(),null),false);
  p.passenger=false;expect(TrainPositionSync.eligible(p,t,null),true);p.passenger=true;
  p.vehicle=new Entity();expect(TrainPositionSync.eligible(p,t,null),true);p.vehicle=t;
  t.world.client=false;expect(TrainPositionSync.eligible(p,t,null),false);t.world.client=true;
  p.world=new net.minecraft.world.level.Level();expect(TrainPositionSync.eligible(p,t,null),false);p.world=t.world;
  t.removed=true;expect(TrainPositionSync.eligible(p,t,null),false);t.removed=false;
  t.validForRender=false;expect(TrainPositionSync.eligible(p,t,null),false);t.validForRender=true;
  var saved=t.carriage;t.carriage=null;expect(TrainPositionSync.eligible(p,t,null),false);t.carriage=saved;
  t.carriage.train.derailed=true;expect(TrainPositionSync.eligible(p,t,null),false);t.carriage.train.derailed=false;
  expect(TrainPositionSync.eligible(p,t,new Vec3(64,0,0)),true);
  expect(TrainPositionSync.eligible(p,t,new Vec3(64.001,0,0)),false);
  expect(TrainPositionSync.eligible(p,t,new Vec3(Double.NaN,0,0)),false);
  expect(TrainPositionSync.eligible(p,t,new Vec3(Double.POSITIVE_INFINITY,0,0)),false);
  expect(TrainPositionSync.selectBranch(t,false,new Vec3(.4,0,0),true),true);
  expect(TrainPositionSync.selectBranch(t,false,null,false),true);
  expect(TrainPositionSync.selectBranch(new Entity(),false,null,false),false);
  expect(TrainPositionSync.selectBranch(new Entity(),true,null,false),true);
  expect(TrainPositionSync.selectBranch(t,false,new Vec3(65,0,0),true),false);
  // External observers, other carriages and state transitions must use the same
  // interpolation owner without granting the client global entity authority.
  p.passenger=false;p.vehicle=null;
  expect(TrainPositionSync.eligible(p,t,null),true);
  expect(TrainPositionSync.selectBranch(t,false,new Vec3(.4,0,0),true),true);
  expect(TrainPositionSync.selectBranch(t,false,null,false),true);
  var other=new CarriageContraptionEntity();other.world=p.world;
  p.vehicle=other;p.passenger=true;
  expect(TrainPositionSync.eligible(p,t,null),true);
  t.firstPositionUpdate=true;expect(TrainPositionSync.eligible(p,t,null),false);
  expect(TrainPositionSync.selectBranch(t,false,null,false),false);t.firstPositionUpdate=false;
  var originalTrain=t.carriage.train;t.carriage.train=null;
  expect(TrainPositionSync.eligible(p,t,null),false);t.carriage.train=originalTrain;
  p.vehicle=null;p.passenger=false;
  expect(TrainPositionSync.selectBranch(t,false,new Vec3(65,0,0),true),false);
  t.carriage.train.derailed=true;expect(TrainPositionSync.selectBranch(t,false,null,false),false);t.carriage.train.derailed=false;
  t.removed=true;expect(TrainPositionSync.selectBranch(t,false,null,false),false);t.removed=false;
  // Bound diagnostics must include the observer case and release old worlds.
  TrainPositionSync.selectBranch(t,false,null,false);TrainPositionSync.report();
  expect("observer".equals(org.slf4j.LoggerFactory.lastRole),true);
  var observed=TrainPositionSync.class.getDeclaredField("observedTrain");observed.setAccessible(true);
  expect(observed.get(null)==t,true);
  p.world=new net.minecraft.world.level.Level();TrainPositionSync.report();
  expect(observed.get(null)==null,true);p.world=t.world;
  TrainPositionSync.selectBranch(t,false,null,false);
  Minecraft.getInstance().player=null;TrainPositionSync.report();
  expect(observed.get(null)==null,true);Minecraft.getInstance().player=p;
  p.vehicle=t;p.passenger=true;
  // Invoke both private wrappers from the actual compiled Mixin. Original calls
  // must occur exactly once, and global entity authority must remain false.
  var mixin=new de.romanglos.mcj.createtrains.mixin.ClientTrainPositionMixin(){};
  var type=de.romanglos.mcj.createtrains.mixin.ClientTrainPositionMixin.class;
  var full=type.getDeclaredMethod("mcj$keepCreateFullSync",Entity.class,
   com.llamalad7.mixinextras.injector.wrapoperation.Operation.class,
   net.minecraft.network.protocol.game.ClientboundEntityPositionSyncPacket.class);full.setAccessible(true);
  var delta=type.getDeclaredMethod("mcj$keepCreateDeltaSync",Entity.class,
   com.llamalad7.mixinextras.injector.wrapoperation.Operation.class,
   net.minecraft.network.protocol.game.ClientboundMoveEntityPacket.class);delta.setAccessible(true);
  int[] calls={0};com.llamalad7.mixinextras.injector.wrapoperation.Operation<Boolean> op=args->{if(args.length!=1)throw new AssertionError();calls[0]++;return false;};
  var packet=new net.minecraft.network.protocol.game.ClientboundEntityPositionSyncPacket(()->new Vec3(.4,0,0));
  expect((Boolean)full.invoke(mixin,t,op,packet),true);
  packet=new net.minecraft.network.protocol.game.ClientboundEntityPositionSyncPacket(()->new Vec3(65,0,0));
  expect((Boolean)full.invoke(mixin,t,op,packet),false);
  expect((Boolean)delta.invoke(mixin,t,op,new net.minecraft.network.protocol.game.ClientboundMoveEntityPacket()),true);
  expect((Boolean)delta.invoke(mixin,new Entity(),op,new net.minecraft.network.protocol.game.ClientboundMoveEntityPacket()),false);
  expect(calls[0]==4,true);expect(t.isLocalInstanceAuthoritative(),false);
  // Force elapsed-time deadlines in the test, without waiting or changing the candidate.
  var next=TrainPositionSync.class.getDeclaredField("nextReport");next.setAccessible(true);
  for(int i=0;i<20;i++){next.setLong(null,0);TrainPositionSync.report();}
  if(org.slf4j.LoggerFactory.lines!=12)throw new AssertionError("log bound");
  System.out.println("position_contract_passed cases="+cases+" reports=12");
 }
}'''}
paths=[]
for name,source in sources.items():
    path=fixture/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source,encoding='utf-8');paths.append(path)
classes=fixture/'classes';classes.mkdir(exist_ok=True)
run([str(jdk/'javac.exe'),'-proc:none','-cp',str(jar),'-d',str(classes),*map(str,paths)])
gate=run([str(jdk/'java.exe'),'-cp',str(classes)+';'+str(jar),'PositionContract'])
assert gate.startswith('position_contract_passed cases=') and ' reports=12' in gate,gate
assert int(gate.split('cases=')[1].split()[0])>=40

# Negative control: the already accepted 1.0.4 must leave the observer path off.
regression=fixture/'ObserverRegression.java'
regression.write_text("""public class ObserverRegression {
 public static void main(String[] args) {
  var p=new net.minecraft.client.player.LocalPlayer();p.vehicle=null;p.passenger=false;
  var t=new com.simibubi.create.content.trains.entity.CarriageContraptionEntity();p.world=t.world;
  net.minecraft.client.Minecraft.getInstance().player=p;
  System.out.println("observer_protected="+de.romanglos.mcj.createtrains.TrainPositionSync.selectBranch(t,false,null,false));
 }
}""",encoding='utf-8')
run([str(jdk/'javac.exe'),'-proc:none','-cp',str(classes)+';'+str(jar),'-d',str(classes),str(regression)])
old_observer=run([str(jdk/'java.exe'),'-cp',str(classes)+';'+str(args.baseline_jar.resolve()),'ObserverRegression'])
new_observer=run([str(jdk/'java.exe'),'-cp',str(classes)+';'+str(jar),'ObserverRegression'])
assert old_observer=='observer_protected=false',old_observer
assert new_observer=='observer_protected=true',new_observer

# Copy the actual 26.3 Entity methods with ASM into a minimal fixture. Only the
# owning class is renamed. No movement/interpolation instruction is recreated.
bytecode=fixture/'BytecodeContract.java'
bytecode.write_text('''import java.nio.file.*;import java.util.*;import java.util.jar.*;
import org.objectweb.asm.*;import org.objectweb.asm.tree.*;
import net.minecraft.world.entity.*;import net.minecraft.world.phys.Vec3;
public class BytecodeContract {
 static ClassNode read(JarFile jar,String name)throws Exception {
  var n=new ClassNode();new ClassReader(jar.getInputStream(jar.getJarEntry(name+".class"))).accept(n,0);return n;}
 static class Loader extends ClassLoader {Class<?> define(byte[] b){return defineClass("MotionFixture",b,0,b.length);}}
 static void check(boolean v){if(!v)throw new AssertionError();}
 static MethodNode method(ClassNode n,String name,String desc){return n.methods.stream().filter(m->m.name.equals(name)&&m.desc.equals(desc)).findFirst().orElseThrow();}
 public static void main(String[] a)throws Exception {
  try(var jar=new JarFile(a[0])) {
   var entity=read(jar,"net/minecraft/world/entity/Entity");
   var packet=read(jar,"net/minecraft/client/multiplayer/ClientPacketListener");
   String[] handlers={"handleEntityPositionSync","handleMoveEntity"};
   int calls=0;
   for(String h:handlers) {
    var m=packet.methods.stream().filter(x->x.name.equals(h)).findFirst().orElseThrow();int count=0;
    for(var ins:m.instructions)if(ins instanceof MethodInsnNode c&&c.owner.equals("net/minecraft/world/entity/Entity")&&c.name.equals("isLocalInstanceAuthoritative")&&c.desc.equals("()Z"))count++;
    check(count==1);calls+=count;
   }
   // Verify ordinary full sync updates the codec before its authority branch.
   var full=packet.methods.stream().filter(x->x.name.equals(handlers[0])).findFirst().orElseThrow();
   int codec=-1,branch=-1,snap=-1,rider=-1,old=-1;
   for(int i=0;i<full.instructions.size();i++)if(full.instructions.get(i)instanceof MethodInsnNode c){
    if(c.name.equals("setBase"))codec=i;if(c.name.equals("isLocalInstanceAuthoritative"))branch=i;
    if(c.name.equals("snapTo"))snap=i;if(c.name.equals("positionRider"))rider=i;if(c.name.equals("setOldPosAndRot"))old=i;}
   check(codec>=0&&codec<branch&&snap>branch&&rider>snap&&old>rider);
   var jump=(JumpInsnNode)full.instructions.get(branch+1);
   check(jump.getOpcode()==Opcodes.IFNE&&full.instructions.indexOf(jump.label)>old);
   // Keep actual method bodies, renaming only their Entity owner to this fixture.
   var dest=new ClassNode();dest.version=Opcodes.V25;dest.access=Opcodes.ACC_PUBLIC;dest.name="MotionFixture";dest.superName="java/lang/Object";
   var cw=new ClassWriter(ClassWriter.COMPUTE_MAXS);
   for(String field:new String[]{"position","interpolationHandler","xo","yo","zo","xOld","yOld","zOld","xRotO","yRotO"}){
    var f=entity.fields.stream().filter(x->x.name.equals(field)).findFirst().orElseThrow();dest.fields.add(new FieldNode(Opcodes.ACC_PUBLIC,f.name,f.desc,null,null));}
   String[][] methods={{"moveOrInterpolateTo","(Lnet/minecraft/world/entity/PositionPath;FFZ)V"},
    {"setOldPosAndRot","()V"},{"setOldPos","()V"},{"setOldPos","(Lnet/minecraft/world/phys/Vec3;)V"},
    {"setOldRot","()V"},{"setOldRot","(FF)V"},{"getEyePosition","(F)Lnet/minecraft/world/phys/Vec3;"}};
   for(var spec:methods){var m=method(entity,spec[0],spec[1]);m.access=Opcodes.ACC_PUBLIC;
    for(var ins:m.instructions){if(ins instanceof FieldInsnNode f&&f.owner.equals(entity.name))f.owner=dest.name;
     if(ins instanceof MethodInsnNode c&&c.owner.equals(entity.name))c.owner=dest.name;}
    dest.methods.add(m);}
   // Fixture accessors supply state; the tested methods above are unchanged MC bytecode.
   var ctor=new MethodNode(Opcodes.ACC_PUBLIC,"<init>","()V",null,null);ctor.visitCode();ctor.visitVarInsn(Opcodes.ALOAD,0);ctor.visitMethodInsn(Opcodes.INVOKESPECIAL,"java/lang/Object","<init>","()V",false);ctor.visitInsn(Opcodes.RETURN);ctor.visitMaxs(1,1);dest.methods.add(ctor);
   for(String axis:new String[]{"X","Y","Z"}){var m=new MethodNode(Opcodes.ACC_PUBLIC,"get"+axis,"()D",null,null);m.visitCode();m.visitVarInsn(Opcodes.ALOAD,0);m.visitFieldInsn(Opcodes.GETFIELD,dest.name,"position","Lnet/minecraft/world/phys/Vec3;");m.visitFieldInsn(Opcodes.GETFIELD,"net/minecraft/world/phys/Vec3",axis.toLowerCase(),"D");m.visitInsn(Opcodes.DRETURN);m.visitMaxs(2,1);dest.methods.add(m);}
   for(String n:new String[]{"getYRot","getXRot","getEyeHeight"}){var m=new MethodNode(Opcodes.ACC_PUBLIC,n,"()F",null,null);m.visitCode();m.visitInsn(Opcodes.FCONST_0);m.visitInsn(Opcodes.FRETURN);m.visitMaxs(1,1);dest.methods.add(m);}
   var set=new MethodNode(Opcodes.ACC_PUBLIC,"setPos","(Lnet/minecraft/world/phys/Vec3;)V",null,null);set.visitCode();set.visitVarInsn(Opcodes.ALOAD,0);set.visitVarInsn(Opcodes.ALOAD,1);set.visitFieldInsn(Opcodes.PUTFIELD,dest.name,"position","Lnet/minecraft/world/phys/Vec3;");set.visitInsn(Opcodes.RETURN);set.visitMaxs(2,2);dest.methods.add(set);
   var rot=new MethodNode(Opcodes.ACC_PUBLIC,"setRot","(FF)V",null,null);rot.visitCode();rot.visitInsn(Opcodes.RETURN);rot.visitMaxs(0,3);dest.methods.add(rot);
   dest.accept(cw);Class<?> type=new Loader().define(cw.toByteArray());var instance=type.getConstructor().newInstance();
   var pos=type.getField("position");var interpolation=type.getField("interpolationHandler");
   pos.set(instance,new Vec3(.4,0,0));interpolation.set(instance,InterpolationHandler.NO_OP);
   var path=PositionPath.of(new Vec3(.8,0,0));
   type.getMethod("moveOrInterpolateTo",PositionPath.class,float.class,float.class,boolean.class).invoke(instance,path,0f,0f,true);
   check(((Vec3)pos.get(instance)).x==.8); // NO_OP actually snaps to the vanilla position.
   pos.set(instance,new Vec3(0,0,0));type.getMethod("setOldPosAndRot").invoke(instance);
   pos.set(instance,new Vec3(.4,0,0));var eye=type.getMethod("getEyePosition",float.class);
   double before=((Vec3)eye.invoke(instance,.5f)).x;
   type.getMethod("setOldPosAndRot").invoke(instance);double after=((Vec3)eye.invoke(instance,.5f)).x;
   check(before==.2&&after==.4);
   System.out.println("actual_bytecode_passed ordinary_handler_sites="+calls+" no_op_snap=true camera_reset_jump=0.2 codec_before_branch=true");
  }
 }
}''',encoding='utf-8')
lines=(build/'javac.args').read_text().splitlines()
cp=lines[lines.index('"-cp"')+1].strip('"')
# Put ASM 9.11 first (older cached copies cannot read Java 25).
libs=args.libraries.resolve()
asm=sorted((libs/'org/ow2/asm').glob('*/9.11/*.jar'))
actual_cp=';'.join(map(str,asm))+';'+cp
actual_classes=fixture/'actual-classes';actual_classes.mkdir(exist_ok=True)
args=['-proc:none','-cp',actual_cp,'-d',str(actual_classes),str(bytecode)]
argfile=fixture/'javac-actual.args';argfile.write_text('\n'.join('"'+a.replace('\\','/')+'"' for a in args))
run([str(jdk/'javac.exe'),'@'+str(argfile)])
mc=libs/'net/neoforged/minecraft-client-patched/26.3.0.99/minecraft-client-patched-26.3.0.99.jar'
args=['-cp',str(actual_classes)+';'+actual_cp,'BytecodeContract',str(mc)]
argfile=fixture/'java-actual.args';argfile.write_text('\n'.join('"'+a.replace('\\','/')+'"' for a in args))
actual=run([str(jdk/'java.exe'),'@'+str(argfile)])
assert actual=='actual_bytecode_passed ordinary_handler_sites=2 no_op_snap=true camera_reset_jump=0.2 codec_before_branch=true',actual
with zipfile.ZipFile(jar)as z:
    config=json.loads(z.read('mcj-create-trains.mixins.json'))
    assert config['client']==['ClientTrainPositionMixin']
    assert not any('ConnectionTraceMixin' in n or 'LocalPlayerTrainMixin' in n for n in z.namelist())
    mixin=z.read('META-INF/sources/ClientTrainPositionMixin.java').decode()
    assert 'handleMoveVehicle' not in mixin and 'handleTeleportEntity' not in mixin
report=dict(observer_negative_control_104=old_observer,observer_candidate_105=new_observer,
    candidate_sha256=hashlib.sha256(jar.read_bytes()).hexdigest(),reproducible_build=True,
    built_helper_against_matching_api_stubs=gate,actual_mc_bytecode_reproduction=actual,
    only_configured_mixin='ClientTrainPositionMixin',ordinary_packet_call_sites=2,
    large_full_sync_recovery_preserved=True,teleport_and_vehicle_handlers_untouched=True,
    entity_authority_methods_unchanged=True,no_outgoing_packet_filter=True,
    log_reports_bounded=12,full_game_mixin_transformation_tested=False,real_driving_tested=False)
(root/'position-contract-proof.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

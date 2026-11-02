"""Generate server-side regression probes in a separate, disposable build tree.

The probes require a real connected test player and an explicit plan file. They
must only be installed in a disposable server; they are never shipped as guards.
"""
from pathlib import Path
import argparse,json,re,shutil

PROBE=r'''package de.romanglos.mcjprobe;
import com.google.gson.*;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.network.protocol.game.ServerboundEditBookPacket;
import net.minecraft.network.protocol.game.ServerboundSetCreativeModeSlotPacket;
import net.minecraft.network.protocol.game.ServerboundPlayerActionPacket;
import net.minecraft.server.network.FilteredText;
import net.minecraft.world.level.GameType;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.ItemStack;
import net.minecraft.core.Direction;
import de.romanglos.mcjprobe.mixin.ProbeBookAccess;
import java.nio.file.*;
import java.util.*;

public final class Probe {
    public static boolean payloadActive,payloadBrand,miningActive,attackActive;
    public static int payloadCalls,miningCalls,attackCalls;
    private static final Path PLAN=Path.of("/mcj-control/reports/probe-plan.json");
    private static final Path RESULT=Path.of("/mcj-control/reports/probe-result.json");
    private static final Gson JSON=new GsonBuilder().setPrettyPrinting().create();
    private static String last="";
    private static int remaining;
    private static Runnable completion;
    private static JsonObject result;
    private static void save(){
        try{Path temporary=RESULT.resolveSibling("probe-result.tmp");Files.writeString(temporary,JSON.toJson(result));Files.move(temporary,RESULT,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}
        catch(Exception failure){throw new IllegalStateException("Cannot retain probe result",failure);}
    }
    private static boolean visitor(ServerPlayer player)throws Exception{
        return (boolean)Class.forName("de.romanglos.mcj.Guard").getMethod("visitor",ServerPlayer.class).invoke(null,player);
    }
    private static void finish(boolean observed,boolean expected){
        result.addProperty("observed",observed);result.addProperty("expected",expected);
        result.addProperty("passed",observed==expected);result.addProperty("state","completed");save();
    }
    public static void tick(MinecraftServer server){
        try{
            if(remaining>0){if(--remaining==0){Runnable next=completion;completion=null;next.run();}return;}
            if(!Files.isRegularFile(PLAN)||Files.size(PLAN)>8192)return;
            JsonObject plan=JsonParser.parseString(Files.readString(PLAN)).getAsJsonObject();String id=plan.get("id").getAsString();
            if(id.equals(last))return;
            ServerPlayer player=server.getPlayerList().getPlayer(UUID.fromString(plan.get("uuid").getAsString()));
            if(player==null)return;
            boolean restricted=visitor(player);if(restricted!=plan.get("visitor").getAsBoolean())return;
            last=id;String action=plan.get("action").getAsString();result=new JsonObject();
            result.addProperty("id",id);result.addProperty("action",action);result.addProperty("visitor",restricted);
            result.addProperty("connected_player",player.getUUID().toString());result.addProperty("state","running");save();
            ItemStack previous=player.getInventory().getItem(0).copy();GameType mode=player.gameMode.getGameModeForPlayer();
            switch(action){
                case "creative_slot":
                    player.getInventory().setItem(0,ItemStack.EMPTY);player.setGameMode(GameType.CREATIVE);
                    player.connection.handleSetCreativeModeSlot(new ServerboundSetCreativeModeSlotPacket(36,new ItemStack(Items.DIAMOND,5)));
                    boolean changed=player.getInventory().getItem(0).is(Items.DIAMOND);
                    player.getInventory().setItem(0,previous);player.setGameMode(mode);finish(changed,!restricted);break;
                case "book_sign":
                case "book_commit":
                    player.getInventory().setItem(0,new ItemStack(Items.WRITABLE_BOOK));
                    if(action.equals("book_sign"))player.connection.handleEditBook(new ServerboundEditBookPacket(0,List.of("regression"),Optional.of("regression")));
                    else ((ProbeBookAccess)player.connection).mcj$probeSignBook(FilteredText.passThrough("regression"),List.of(FilteredText.passThrough("regression")),0);
                    remaining=40;completion=()->{boolean signed=player.getInventory().getItem(0).is(Items.WRITTEN_BOOK);player.getInventory().setItem(0,previous);finish(signed,!restricted);};break;
                case "payload":
                case "payload_alt":
                case "payload_brand":
                    payloadCalls=0;payloadActive=true;payloadBrand=action.equals("payload_brand");
                    try{Payloads.invoke(player,action);}finally{payloadActive=false;}
                    finish(payloadCalls==1,payloadBrand||!restricted);break;
                case "mining":
                    miningCalls=0;miningActive=true;
                    try{player.gameMode.handleBlockBreakAction(player.blockPosition(),ServerboundPlayerActionPacket.Action.START_DESTROY_BLOCK,Direction.UP,256,0);}finally{miningActive=false;}
                    finish(miningCalls==1,!restricted);break;
                case "attack":
                    attackCalls=0;attackActive=true;
                    try{player.attack(player);}finally{attackActive=false;}
                    finish(attackCalls==1,!restricted);break;
                default:throw new IllegalArgumentException("Unknown regression action");
            }
        }catch(Exception failure){
            payloadActive=miningActive=attackActive=false;remaining=0;completion=null;
            if(result==null)result=new JsonObject();result.addProperty("state","failed");result.addProperty("error",failure.toString());save();
        }
    }
}
'''

def mixin(target,method,body,callback_type='CallbackInfo',priority=2000,remap=''):
    return f'''package de.romanglos.mcjprobe.mixin;
import de.romanglos.mcjprobe.Probe;
import net.minecraft.server.MinecraftServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.{callback_type};
@Mixin(value={target}.class,priority={priority}{remap})
public abstract class Probe{method}Mixin {{
    @Inject(method="{method}",at=@At("{'RETURN' if method=='tickChildren' else 'HEAD'}"),cancellable=true)
    private void probe$call({callback_type} callback){{{body}}}
}}
'''

def generate(repository,output):
    assert not output.exists();output.mkdir(parents=True)
    modules=[f'guard-{loader}-{version}' for loader in ['fabric','forge'] for version in ['1201','1211','263']]+['guard-neoforge','guard-neoforge-1211']
    for module in modules:
        original=repository/module;target=output/('probe-'+module);target.mkdir()
        for name in ['build.gradle','settings.gradle','gradle.properties']:
            if (original/name).is_file():shutil.copyfile(original/name,target/name)
        gradle=(target/'build.gradle').read_text().replace('mcj_guard','mcj_probe')
        gradle=re.sub(r"version\s*=\s*'[^']+'","version='0.0.3'",gradle,count=1)
        gradle=re.sub(r"tasks.register\('networkAccessCheck',JavaExec\)\s*\{[^}]*\}\s*check.dependsOn networkAccessCheck",'',gradle,flags=re.S)
        (target/'build.gradle').write_text(gradle)
        java=target/'src/main/java/de/romanglos/mcjprobe';java.mkdir(parents=True)
        mixin_java=java/'mixin';mixin_java.mkdir()
        resources=target/'src/main/resources';resources.mkdir(parents=True)
        modern=module in ['guard-forge-1211','guard-forge-263'];remap=',remap=false' if modern else ''
        latest=module.endswith('263') or module=='guard-neoforge'
        pre1201=module.endswith('1201')
        probe=PROBE
        if not latest and not module.startswith('guard-neoforge'):
            probe=probe.replace('import net.minecraft.network.protocol.game.ServerboundEditBookPacket;',
                'import net.minecraft.network.protocol.game.ServerboundEditBookPacket;\nimport net.minecraft.network.protocol.game.ServerboundInteractPacket;')
            probe=probe.replace('                case "payload":','''                case "camera":
                    player.setGameMode(GameType.SPECTATOR);
                    var target=player.level().getEntities(player,player.getBoundingBox().inflate(8),entity->entity.getTags().contains("mcj_probe_camera")).stream().findFirst().orElseThrow();
                    player.connection.handleInteract(ServerboundInteractPacket.createAttackPacket(target,false));
                    boolean followed=player.getCamera()==target;player.setCamera(player);player.setGameMode(mode);finish(followed,true);break;
                case "payload":''')
        (java/'Probe.java').write_text(probe)
        (mixin_java/'ProbetickChildrenMixin.java').write_text(mixin('net.minecraft.server.MinecraftServer','tickChildren','Probe.tick((MinecraftServer)(Object)this);',priority=3000,remap=remap))
        (mixin_java/'ProbehandleBlockBreakActionMixin.java').write_text(mixin('net.minecraft.server.level.ServerPlayerGameMode','handleBlockBreakAction','if(Probe.miningActive){Probe.miningCalls++;callback.cancel();}',remap=remap))
        attack_class='net.minecraft.world.entity.player.Player' if latest else 'net.minecraft.server.level.ServerPlayer'
        (mixin_java/'ProbeattackMixin.java').write_text(mixin(attack_class,'attack','if(Probe.attackActive){Probe.attackCalls++;callback.cancel();}',remap=remap))
        payload_source=(original/'src/main/java/de/romanglos/mcj/mixin/GuardPayloadMixin.java').read_text()
        payload_class='net.minecraft.server.network.'+('ServerCommonPacketListenerImpl' if '@Mixin(ServerCommonPacketListenerImpl.class)' in payload_source or 'value=ServerCommonPacketListenerImpl.class' in payload_source else 'ServerGamePacketListenerImpl')
        # Fabric consumes even unknown payloads at its own HEAD injection.
        # Count after the guard (500), before that dispatcher (1000), so the
        # authorized-player control must reach the same measured boundary.
        payload_priority=750 if module.startswith('guard-fabric') else 2000
        (mixin_java/'ProbehandleCustomPayloadMixin.java').write_text(mixin(payload_class,'handleCustomPayload','if(Probe.payloadActive){Probe.payloadCalls++;if(!Probe.payloadBrand)callback.cancel();}',priority=payload_priority,remap=remap))
        (mixin_java/'ProbeBookAccess.java').write_text('''package de.romanglos.mcjprobe.mixin;
import net.minecraft.server.network.FilteredText;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;
import java.util.List;
@Mixin(value=ServerGamePacketListenerImpl.classREMAP)
public interface ProbeBookAccess {
    @Invoker("signBook") void mcj$probeSignBook(FilteredText title,List<FilteredText> contents,int slot);
}
'''.replace('REMAP',remap))
        if pre1201:
            payload='''package de.romanglos.mcjprobe;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.network.protocol.game.ServerboundCustomPayloadPacket;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.network.FriendlyByteBuf;
import io.netty.buffer.Unpooled;
public final class Payloads {
    public static void invoke(ServerPlayer player,String action){
        FriendlyByteBuf buffer=new FriendlyByteBuf(Unpooled.buffer());
        boolean brand=action.equals("payload_brand");
        if(brand)buffer.writeUtf("mcj-probe");
        try{
            new ServerboundCustomPayloadPacket(brand?new ResourceLocation("minecraft","brand"):new ResourceLocation("mcj_probe",action.equals("payload_alt")?"boundary_alt":"boundary"),buffer).handle(player.connection);
            if(buffer.refCnt()!=0)throw new IllegalStateException("Packet wrapper did not release its buffer");
        }
        finally{if(buffer.refCnt()>0)buffer.release();}
    }
}
'''
        else:
            identifier='Identifier' if latest else 'ResourceLocation'
            payload='''package de.romanglos.mcjprobe;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.network.protocol.common.ServerboundCustomPayloadPacket;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.network.protocol.common.custom.BrandPayload;
import net.minecraft.resources.IDENTIFIER;
public final class Payloads {
    public record Sample(boolean alternate) implements CustomPacketPayload {
        public static final Type<Sample> TYPE=new Type<>(IDENTIFIER.fromNamespaceAndPath("mcj_probe","boundary"));
        public static final Type<Sample> ALTERNATE=new Type<>(IDENTIFIER.fromNamespaceAndPath("mcj_probe","boundary_alt"));
        public Type<Sample> type(){return alternate?ALTERNATE:TYPE;}
    }
    public static void invoke(ServerPlayer player,String action){player.connection.handleCustomPayload(new ServerboundCustomPayloadPacket(action.equals("payload_brand")?new BrandPayload("mcj-probe"):new Sample(action.equals("payload_alt"))));}
}
'''.replace('IDENTIFIER',identifier)
        (java/'Payloads.java').write_text(payload)
        original_mixins=json.loads((original/'src/main/resources/mcj_guard.mixins.json').read_text())
        compatibility=original_mixins['compatibilityLevel']
        mixins=['ProbetickChildrenMixin','ProbehandleBlockBreakActionMixin','ProbeattackMixin','ProbehandleCustomPayloadMixin','ProbeBookAccess']
        configuration={'required':True,'minVersion':'0.8','package':'de.romanglos.mcjprobe.mixin','compatibilityLevel':compatibility,'mixins':mixins,'injectors':{'defaultRequire':1}}
        if original_mixins.get('refmap'):configuration['refmap']=original_mixins['refmap'].replace('mcj_guard','mcj_probe')
        (resources/'mcj_probe.mixins.json').write_text(json.dumps(configuration,indent=2))
        if module.startswith('guard-fabric'):
            value=json.loads((original/'src/main/resources/fabric.mod.json').read_text())
            for key in ['entrypoints','mixins']:value.pop(key,None)
            value.update(id='mcj_compat_probe',name='MCJ compatibility regression probe',version='0.0.3',mixins=['mcj_probe.mixins.json'],environment='server')
            (resources/'fabric.mod.json').write_text(json.dumps(value,indent=2))
        else:
            filename='META-INF/neoforge.mods.toml' if module.startswith('guard-neoforge') else 'META-INF/mods.toml'
            metadata=(original/'src/main/resources'/filename).read_text().replace('mcj_guard.mixins.json','mcj_probe.mixins.json').replace('mcj_guard','mcj_compat_probe')
            (resources/'META-INF').mkdir();(resources/filename).write_text(metadata)
            namespace='net.neoforged' if module.startswith('guard-neoforge') else 'net.minecraftforge'
            (java/'ProbeEntrypoint.java').write_text(f'package de.romanglos.mcjprobe;\nimport {namespace}.fml.common.Mod;\n@Mod("mcj_compat_probe")\npublic final class ProbeEntrypoint {{ public ProbeEntrypoint(){{}} }}\n')
    return modules

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    repository=Path(__file__).resolve().parents[2]
    print(json.dumps({'modules':generate(repository,args.output.resolve()),'output':str(args.output.resolve())}))

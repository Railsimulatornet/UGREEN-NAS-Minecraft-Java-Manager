package de.romanglos.mcj.mixin;
import de.romanglos.mcj.Guard;
import net.minecraft.server.MinecraftServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
@Mixin(value=MinecraftServer.class,remap=false)
public abstract class GuardServerTickMixin {
    @Inject(method="tickChildren",at=@At("RETURN"))
    private void mcj$tick(CallbackInfo callback){Guard.tick((MinecraftServer)(Object)this);}
}

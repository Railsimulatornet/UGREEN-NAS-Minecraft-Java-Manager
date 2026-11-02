package de.romanglos.mcj.mixin;

import de.romanglos.mcj.Guard;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value=ServerPlayer.class,priority=500)
public abstract class GuardServerPlayerMixin {
    @Inject(method="attack",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorCamera(Entity target,CallbackInfo callback){
        ServerPlayer player=(ServerPlayer)(Object)this;
        if(Guard.visitor(player)){
            // This is the native pre-26.3 spectator branch, before mod callbacks.
            if(player.isSpectator())player.setCamera(target);
            callback.cancel();
        }
    }
}

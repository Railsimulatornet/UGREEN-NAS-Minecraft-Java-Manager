package de.romanglos.mcj.mixin;

import de.romanglos.mcj.Guard;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value=Player.class,priority=500)
public abstract class GuardCombatMixin {
    @Inject(method="attack",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorDirectAttack(Entity target,CallbackInfo callback){
        if((Object)this instanceof ServerPlayer player && Guard.visitor(player))callback.cancel();
    }
}

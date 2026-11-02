package de.romanglos.mcj.mixin;
import de.romanglos.mcj.Guard;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import net.minecraft.network.protocol.game.ServerboundCustomPayloadPacket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
@Mixin(value=ServerGamePacketListenerImpl.class,priority=500)
public abstract class GuardPayloadMixin {
    @Shadow public ServerPlayer player;
    @Inject(method="handleCustomPayload",at=@At("HEAD"),cancellable=true)
    private void mcj$payload(ServerboundCustomPayloadPacket packet,CallbackInfo callback){
        if(Guard.visitor(player) && !packet.getIdentifier().toString().equals("minecraft:brand")){
            callback.cancel();
        }
    }
}

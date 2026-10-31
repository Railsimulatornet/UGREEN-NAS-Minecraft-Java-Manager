package de.romanglos.mcj.mixin;

import de.romanglos.mcj.Guard;
import net.minecraft.network.protocol.common.ServerboundCustomPayloadPacket;
import net.minecraft.server.network.ServerCommonPacketListenerImpl;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ServerCommonPacketListenerImpl.class)
public abstract class GuardPayloadMixin {
    @Inject(method="handleCustomPayload",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorPayload(ServerboundCustomPayloadPacket packet,CallbackInfo callback){
        // Configuration-phase loader negotiation is unaffected. During play,
        // unknown players cannot invoke mod-specific world-changing handlers.
        if((Object)this instanceof ServerGamePacketListenerImpl handler && Guard.visitor(handler.player)){
            if(!packet.payload().type().id().toString().equals("minecraft:brand"))callback.cancel();
        }
    }
}

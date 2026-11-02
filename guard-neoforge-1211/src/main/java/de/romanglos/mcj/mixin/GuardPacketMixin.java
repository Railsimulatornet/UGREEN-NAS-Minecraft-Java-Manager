package de.romanglos.mcj.mixin;

import de.romanglos.mcj.Guard;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import net.minecraft.network.protocol.game.ServerboundChatCommandPacket;
import net.minecraft.network.protocol.game.ServerboundChatCommandSignedPacket;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ServerGamePacketListenerImpl.class)
public abstract class GuardPacketMixin {
    @Shadow public ServerPlayer player;

    @Inject(method="handleChatCommand",at=@At("HEAD"),cancellable=true)
    private void mcj$unsignedCommand(ServerboundChatCommandPacket packet,CallbackInfo callback){
        if(Guard.visitor(player))callback.cancel();
    }

    @Inject(method="handleSignedChatCommand",at=@At("HEAD"),cancellable=true)
    private void mcj$signedCommand(ServerboundChatCommandSignedPacket packet,CallbackInfo callback){
        if(Guard.visitor(player))callback.cancel();
    }


    @Inject(method={"handleEditBook","updateBookContents","signBook"},at=@At("HEAD"),cancellable=true)
    private void mcj$visitorBook(CallbackInfo callback){
        if(Guard.visitor(player))callback.cancel();
    }

    @Inject(method="handleSetCreativeModeSlot",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorCreativeSlot(CallbackInfo callback){
        if(Guard.visitor(player))callback.cancel();
    }
}

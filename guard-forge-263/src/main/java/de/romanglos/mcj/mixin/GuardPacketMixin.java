package de.romanglos.mcj.mixin;

import de.romanglos.mcj.Guard;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import net.minecraft.network.protocol.game.ServerboundChatCommandPacket;
import net.minecraft.network.protocol.game.ServerboundChatCommandSignedPacket;
import net.minecraft.network.protocol.game.ServerboundChangeGameModePacket;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ServerboundAttackPacket;
import org.spongepowered.asm.mixin.Mixin;
import net.minecraft.network.protocol.game.ServerboundPlayerActionPacket;
import net.minecraft.network.protocol.game.ServerboundInteractPacket;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value=ServerGamePacketListenerImpl.class,priority=500,remap=false)
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

    @Inject(method="handleChangeGameMode",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorMode(ServerboundChangeGameModePacket packet,CallbackInfo callback){
        if(Guard.visitor(player))callback.cancel();
    }

    @Inject(method="handlePlayerAction",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorAction(ServerboundPlayerActionPacket packet,CallbackInfo callback){
        if(!Guard.visitor(player))return;
        // Mining keeps its normal sequence acknowledgement; the GameMode hooks
        // reject both initial callbacks and delayed block destruction.
        switch(packet.getAction().name()){
            case "START_DESTROY_BLOCK", "STOP_DESTROY_BLOCK", "ABORT_DESTROY_BLOCK", "CHANGE_DESTROY_DIRECTION": return;
            default: callback.cancel();
        }
    }

    @Inject(method="handleInteract",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorInteract(ServerboundInteractPacket packet,CallbackInfo callback){
        if(Guard.visitor(player))callback.cancel();
    }
    @Inject(method="handleAttack",at=@At("HEAD"),cancellable=true)
    private void mcj$visitorAttack(ServerboundAttackPacket packet,CallbackInfo callback){
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

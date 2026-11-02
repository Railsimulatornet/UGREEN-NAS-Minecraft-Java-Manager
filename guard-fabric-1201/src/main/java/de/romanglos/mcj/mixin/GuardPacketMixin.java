package de.romanglos.mcj.mixin;

import de.romanglos.mcj.Guard;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import net.minecraft.network.protocol.game.ServerboundChatCommandPacket;
import net.minecraft.network.chat.Component;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.phys.Vec3;
import org.spongepowered.asm.mixin.Mixin;
import net.minecraft.network.protocol.game.ServerboundPlayerActionPacket;
import net.minecraft.network.protocol.game.ServerboundInteractPacket;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value=ServerGamePacketListenerImpl.class,priority=500)
public abstract class GuardPacketMixin {
    @Shadow public ServerPlayer player;

    @Inject(method="handleChatCommand",at=@At("HEAD"),cancellable=true)
    private void mcj$unsignedCommand(ServerboundChatCommandPacket packet,CallbackInfo callback){
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
        if(!Guard.visitor(player))return;
        final boolean[] attack={false};
        packet.dispatch(new ServerboundInteractPacket.Handler(){
            public void onInteraction(InteractionHand hand){}
            public void onInteraction(InteractionHand hand,Vec3 position){}
            public void onAttack(){attack[0]=true;}
        });
        // Preserve native target/range validation and spectator-camera attacks.
        // GuardServerPlayerMixin cancels before any mod attack callback.
        if(!attack[0] || !player.isSpectator())callback.cancel();
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

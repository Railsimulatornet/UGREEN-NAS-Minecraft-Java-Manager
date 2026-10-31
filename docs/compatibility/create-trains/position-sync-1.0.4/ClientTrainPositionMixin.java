package de.romanglos.mcj.createtrains.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import de.romanglos.mcj.createtrains.TrainPositionSync;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.network.protocol.game.ClientboundEntityPositionSyncPacket;
import net.minecraft.network.protocol.game.ClientboundMoveEntityPacket;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

@Mixin(value=ClientPacketListener.class,remap=false)
public abstract class ClientTrainPositionMixin {
    @WrapOperation(method="handleEntityPositionSync(Lnet/minecraft/network/protocol/game/ClientboundEntityPositionSyncPacket;)V",
        at=@At(value="INVOKE",target="Lnet/minecraft/world/entity/Entity;isLocalInstanceAuthoritative()Z"),
        require=1,expect=1,allow=1)
    private boolean mcj$keepCreateFullSync(Entity entity,Operation<Boolean> original,ClientboundEntityPositionSyncPacket packet) {
        return TrainPositionSync.selectBranch(entity,original.call(entity),packet.position().endPosition(),true);
    }

    @WrapOperation(method="handleMoveEntity(Lnet/minecraft/network/protocol/game/ClientboundMoveEntityPacket;)V",
        at=@At(value="INVOKE",target="Lnet/minecraft/world/entity/Entity;isLocalInstanceAuthoritative()Z"),
        require=1,expect=1,allow=1)
    private boolean mcj$keepCreateDeltaSync(Entity entity,Operation<Boolean> original,ClientboundMoveEntityPacket packet) {
        return TrainPositionSync.selectBranch(entity,original.call(entity),null,false);
    }
}

package de.romanglos.mcj.mixin;
import de.romanglos.mcj.Guard;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.ServerPlayerGameMode;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.BlockHitResult;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Final;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.protocol.game.ServerboundPlayerActionPacket;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value=ServerPlayerGameMode.class,priority=500)
public abstract class GuardInteractionMixin {
    @Shadow @Final protected ServerPlayer player;
    @Inject(method="useItemOn",at=@At("HEAD"),cancellable=true)
    private void mcj$blockContainer(ServerPlayer player,Level level,ItemStack stack,InteractionHand hand,BlockHitResult hit,CallbackInfoReturnable<InteractionResult> result){
        if(Guard.visitor(player))result.setReturnValue(InteractionResult.FAIL);
    }
    @Inject(method="useItem",at=@At("HEAD"),cancellable=true)
    private void mcj$blockItem(ServerPlayer player,Level level,ItemStack stack,InteractionHand hand,CallbackInfoReturnable<InteractionResult> result){
        if(Guard.visitor(player))result.setReturnValue(InteractionResult.FAIL);
    }

    @Inject(method="handleBlockBreakAction",at=@At("HEAD"),cancellable=true)
    private void mcj$blockMining(BlockPos position,ServerboundPlayerActionPacket.Action action,Direction direction,int height,int sequence,CallbackInfo callback){
        if(Guard.visitor(player))callback.cancel();
    }
    @Inject(method="destroyBlock",at=@At("HEAD"),cancellable=true)
    private void mcj$blockDelayedDestruction(BlockPos position,CallbackInfoReturnable<Boolean> result){
        if(Guard.visitor(player))result.setReturnValue(false);
    }
}

package de.romanglos.mcj.mixin;
import de.romanglos.mcj.Guard;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.login.ServerboundHelloPacket;
import net.minecraft.server.network.ServerLoginPacketListenerImpl;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ServerLoginPacketListenerImpl.class)
public abstract class GuardLoginMixin {
    @Inject(method="handleHello",at=@At("HEAD"),cancellable=true)
    private void mcj$closeLogin(ServerboundHelloPacket packet,CallbackInfo callback){
        if(Guard.closed()){
            ((ServerLoginPacketListenerImpl)(Object)this).disconnect(Component.literal("Der Zugang zum Server ist vorübergehend gesperrt. Bitte versuche es später erneut. / Server access is temporarily closed. Please try again later."));
            callback.cancel();
        }
    }
}

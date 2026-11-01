package de.romanglos.mcj.mixin;
import de.romanglos.mcj.Guard;
import de.romanglos.mcj.NetworkAccess;
import com.mojang.authlib.GameProfile;
import java.net.SocketAddress;
import net.minecraft.network.chat.Component;
import net.minecraft.server.players.PlayerList;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
@Mixin(value=PlayerList.class,remap=false)
public abstract class GuardPlayerListMixin {
    @Inject(method="canPlayerLogin",at=@At("HEAD"),cancellable=true)
    private void mcj$checkAdmission(SocketAddress address,GameProfile profile,CallbackInfoReturnable<Component> result){
        if(Guard.closed()){result.setReturnValue(Component.literal("Der Zugang zum Server ist vorübergehend gesperrt. Bitte versuche es später erneut. / Server access is temporarily closed. Please try again later."));return;}
        if(!NetworkAccess.allowed(address)){result.setReturnValue(Component.literal("Minecraft-Zugang nur im Heimnetz / Minecraft access is limited to the local network"));return;}
        String reason=Guard.banReason(profile.getId());
        if(reason!=null)result.setReturnValue(Component.literal("Dein Zugang zu diesem Server ist gesperrt. Grund / Your access to this server is blocked. Reason: "+reason));
    }

    @org.spongepowered.asm.mixin.Shadow @org.spongepowered.asm.mixin.Final
    private net.minecraft.server.MinecraftServer server;
    @Inject(method="placeNewPlayer",at=@At("TAIL"))
    private void mcj$joined(net.minecraft.network.Connection connection,net.minecraft.server.level.ServerPlayer player, net.minecraft.server.network.CommonListenerCookie cookie,org.spongepowered.asm.mixin.injection.callback.CallbackInfo callback){
        Guard.login(player,server);
    }
    @Inject(method="remove",at=@At("HEAD"))
    private void mcj$left(net.minecraft.server.level.ServerPlayer player,org.spongepowered.asm.mixin.injection.callback.CallbackInfo callback){
        Guard.logout(player);
    }
}

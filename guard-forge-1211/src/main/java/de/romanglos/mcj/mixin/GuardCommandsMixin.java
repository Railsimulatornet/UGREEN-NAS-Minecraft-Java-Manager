package de.romanglos.mcj.mixin;
import de.romanglos.mcj.RoleCommands;
import net.minecraft.commands.Commands;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
@Mixin(value=Commands.class,remap=false)
public abstract class GuardCommandsMixin {
    @Inject(method="<init>",at=@At("RETURN"))
    private void mcj$register(CallbackInfo callback){RoleCommands.register(((Commands)(Object)this).getDispatcher());}
}

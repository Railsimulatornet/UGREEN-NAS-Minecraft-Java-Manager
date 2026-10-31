package de.romanglos.mcj.createtrains;

import com.simibubi.create.content.trains.entity.CarriageContraptionEntity;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Only selects the existing codec-only branch in two ordinary entity-sync handlers. */
public final class TrainPositionSync {
    private static final Logger LOG=LoggerFactory.getLogger("MCJ-TrainFix");
    private static long syncProtected,deltaProtected,vanillaPassed,nextReport;
    private static int reports;
    private TrainPositionSync() {}

    public static boolean eligible(LocalPlayer player,Entity entity,Vec3 fullSyncPosition) {
        if(player==null || !(entity instanceof CarriageContraptionEntity train)
            || !player.isPassenger() || player.getVehicle()!=train
            || !train.level().isClientSide() || player.level()!=train.level()
            || train.isRemoved() || !train.validForRender || train.getCarriage()==null
            || train.getCarriage().train.derailed) return false;
        // Preserve vanilla's recovery snap for full syncs farther than 64 blocks.
        if(fullSyncPosition!=null) {
            double distance=entity.position().distanceToSqr(fullSyncPosition);
            if(!Double.isFinite(distance) || distance>4096.0) return false;
        }
        return true;
    }

    public static boolean selectBranch(Entity entity,boolean original,Vec3 fullSyncPosition,boolean fullSync) {
        boolean protect=eligible(Minecraft.getInstance().player,entity,fullSyncPosition);
        if(protect) {
            if(fullSync) syncProtected++; else deltaProtected++;
        } else vanillaPassed++;
        return original || protect;
    }

    public static void report() {
        if(reports>=12)return;
        var player=Minecraft.getInstance().player;
        var vehicle=player==null?null:player.getVehicle();
        if(!(vehicle instanceof CarriageContraptionEntity))return;
        long now=System.nanoTime();
        if(now<nextReport)return;
        nextReport=now+5_000_000_000L;
        LOG.info("[MCJ-TrainFix] sample={} mode=create-position-sync eligible={} syncProtected={} deltaProtected={} vanillaPassed={} localAuthority={}",
            ++reports,eligible(player,vehicle,null),syncProtected,deltaProtected,vanillaPassed,
            vehicle.isLocalInstanceAuthoritative());
    }
}

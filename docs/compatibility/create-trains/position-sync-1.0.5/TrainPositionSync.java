package de.romanglos.mcj.createtrains;

import com.simibubi.create.content.trains.entity.CarriageContraptionEntity;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Keeps Create's initialized train interpolation independent of the viewer's seat. */
public final class TrainPositionSync {
    private static final Logger LOG=LoggerFactory.getLogger("MCJ-TrainFix");
    private static long syncProtected,deltaProtected,seatedProtected,observerProtected,vanillaPassed,nextReport;
    private static int reports;
    private static CarriageContraptionEntity observedTrain;
    private TrainPositionSync() {}

    public static boolean eligible(LocalPlayer player,Entity entity,Vec3 fullSyncPosition) {
        if(player==null || !(entity instanceof CarriageContraptionEntity train)
            || !train.level().isClientSide() || player.level()!=train.level()
            || train.isRemoved() || !train.validForRender || train.firstPositionUpdate
            || train.getCarriage()==null || train.getCarriage().train==null
            || train.getCarriage().train.derailed) return false;
        // Initial placement and exceptional recovery continue through vanilla.
        if(fullSyncPosition!=null) {
            double distance=entity.position().distanceToSqr(fullSyncPosition);
            if(!Double.isFinite(distance) || distance>4096.0) return false;
        }
        return true;
    }

    public static boolean selectBranch(Entity entity,boolean original,Vec3 fullSyncPosition,boolean fullSync) {
        var player=Minecraft.getInstance().player;
        boolean protect=eligible(player,entity,fullSyncPosition);
        if(protect) {
            observedTrain=(CarriageContraptionEntity)entity;
            if(fullSync) syncProtected++; else deltaProtected++;
            if(player.getVehicle()==entity) seatedProtected++; else observerProtected++;
        } else vanillaPassed++;
        return original || protect;
    }

    public static void report() {
        var player=Minecraft.getInstance().player;
        if(player==null) {observedTrain=null;return;}
        // Clear stale world references even after the bounded report budget ends.
        if(observedTrain!=null && (observedTrain.isRemoved() || observedTrain.level()!=player.level()))
            observedTrain=null;
        var train=player.getVehicle() instanceof CarriageContraptionEntity seated?seated:observedTrain;
        if(reports>=12 || train==null || !eligible(player,train,null))return;
        long now=System.nanoTime();
        if(now<nextReport)return;
        nextReport=now+5_000_000_000L;
        LOG.info("[MCJ-TrainFix] sample={} role={} eligible=true syncProtected={} deltaProtected={} seatedProtected={} observerProtected={} vanillaPassed={} localAuthority={}",
            ++reports,player.getVehicle()==train?"seated":"observer",syncProtected,deltaProtected,
            seatedProtected,observerProtected,vanillaPassed,train.isLocalInstanceAuthoritative());
    }
}

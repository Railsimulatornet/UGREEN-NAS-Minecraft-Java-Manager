package de.romanglos.mcj.createtrains;

import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HexFormat;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.ModList;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import org.slf4j.LoggerFactory;

@Mod(value="mcj_create_train_fix",dist=Dist.CLIENT)
public final class CreateTrainFix {
    public CreateTrainFix() throws Exception {
        var file=ModList.get().getModFileById("create");
        if(file==null)throw new IllegalStateException("Train correction requires Create Adapted 1.31.");
        String checksum;
        try(var in=Files.newInputStream(file.getFile().getFilePath())) {
            var md=MessageDigest.getInstance("SHA-256");byte[] b=new byte[65536];int n;
            while((n=in.read(b))!=-1)md.update(b,0,n);
            checksum=HexFormat.of().formatHex(md.digest());
        }
        if(!CreateCompatibility.accepts(checksum))
            throw new IllegalStateException("Train correction: unsupported Create file; remove this correction before updating Create.");
        NeoForge.EVENT_BUS.addListener((ClientTickEvent.Post e)->TrainPositionSync.report());
        LoggerFactory.getLogger("MCJ-TrainFix").info("[MCJ-TrainFix] loaded=1.0.5 mode=create-position-sync scope=passengers-and-observers createSha256={} boundedReports=12",checksum);
    }
}

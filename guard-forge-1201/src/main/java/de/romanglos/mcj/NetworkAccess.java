package de.romanglos.mcj;

import com.google.gson.JsonParser;
import java.net.InetSocketAddress;
import java.net.InetAddress;
import java.net.SocketAddress;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

/** Only the controller writes this read-only, hot-reloaded admission policy. */
public final class NetworkAccess {
    private static final Path POLICY=Path.of("/mcj-control/roles/network-access.json");
    public static boolean publicGame(){return publicGame(POLICY);}
    static boolean publicGame(Path policy){
        try {
            if(!Files.exists(policy,LinkOption.NOFOLLOW_LINKS))return true; // existing installations
            if(Files.isSymbolicLink(policy)||!Files.isRegularFile(policy)||Files.size(policy)>4096)return false;
            var value=JsonParser.parseString(Files.readString(policy)).getAsJsonObject().get("public_game");
            return value!=null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isBoolean() && value.getAsBoolean();
        } catch(Exception ignored){return false;}
    }
    public static boolean allowed(SocketAddress remote){return publicGame() || local(remote);}
    static boolean local(SocketAddress remote){
        if(!(remote instanceof InetSocketAddress socket))return false;
        InetAddress address=socket.getAddress();if(address==null)return false;
        if(address.isLoopbackAddress())return true;
        byte[] raw=address.getAddress();
        if(raw.length==4)return (raw[0]&255)==10 || (raw[0]&255)==172 && (raw[1]&255)>=16 && (raw[1]&255)<=31 || (raw[0]&255)==192 && (raw[1]&255)==168;
        return raw.length==16 && ((raw[0]&254)==252); // IPv6 unique local, not link local
    }
    public static String fingerprint(){
        try {
            if(!Files.exists(POLICY,LinkOption.NOFOLLOW_LINKS))return "legacy";
            if(Files.isSymbolicLink(POLICY)||Files.size(POLICY)>4096)return "invalid";
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(POLICY)));
        } catch(Exception ignored){return "invalid";}
    }
}

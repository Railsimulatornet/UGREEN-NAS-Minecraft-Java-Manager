package de.romanglos.mcj;

import com.google.gson.*;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.GameType;
import net.minecraft.server.players.NameAndId;
import net.minecraft.world.InteractionResult;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public final class Guard implements net.fabricmc.api.DedicatedServerModInitializer {
    private static final String BUILD_VERSION=buildVersion();
    private static String buildVersion(){
        Properties value=new Properties();
        try(var input=Guard.class.getResourceAsStream("/mcj-guard-version.properties")){
            if(input==null)throw new IllegalStateException("Guard build metadata missing");
            value.load(input);
            String version=value.getProperty("version","");
            if(!version.matches("[0-9]+\\.[0-9]+\\.[0-9]+"))throw new IllegalStateException("Guard build metadata invalid");
            return version;
        }catch(java.io.IOException error){throw new IllegalStateException("Guard build metadata unreadable",error);}
    }
    private static final Path BASE=Path.of("/mcj-control");
    private static final Gson JSON=new GsonBuilder().setPrettyPrinting().create();
    private static final Map<UUID,JsonObject> PLAYERS=new HashMap<>();
    private static final Set<UUID> RESTRICTED=new HashSet<>();
    private static long lastReport=0, windowStart=System.nanoTime(), ticks=0;
    private static double actualTps=0;
    @Override public void onInitializeServer(){}

    private static JsonObject read(Path path){
        try {
            if(Files.isSymbolicLink(path) || Files.size(path)>1024*1024) return new JsonObject();
            return JsonParser.parseString(Files.readString(path)).getAsJsonObject();
        } catch(Exception ignored){ return new JsonObject(); }
    }
    private static void write(Path path,JsonObject object){
        try {
            Files.createDirectories(path.getParent());
            Path temporary=path.resolveSibling(path.getFileName()+".tmp");
            Files.writeString(temporary,JSON.toJson(object),StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,StandardOpenOption.TRUNCATE_EXISTING);
            Files.move(temporary,path,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        } catch(Exception ignored) { /* Missing/stale heartbeat prevents controller acceptance. */ }
    }
    public static boolean closed(){
        try {
            Path roles=BASE.resolve("roles/roles.json");
            if(Files.isSymbolicLink(roles) || Files.size(roles)>1024*1024)return true;
            JsonObject grants=JsonParser.parseString(Files.readString(roles)).getAsJsonObject();
            for(String id:grants.keySet()){
                if(!UUID.fromString(id).toString().equals(id))return true;
                String value=grants.getAsJsonObject(id).get("role").getAsString();
                if(!Set.of("visitor","player","moderator","administrator").contains(value))return true;
            }
            JsonObject gate=read(BASE.resolve("roles/maintenance.json"));
            return !gate.has("closed") || gate.get("closed").getAsBoolean();
        } catch(Exception ignored){return true;}
    }
    private static JsonObject grant(UUID id){
        try {
            JsonObject data=read(BASE.resolve("roles/roles.json"));
            return data.has(id.toString())?data.getAsJsonObject(id.toString()):new JsonObject();
        } catch(Exception ignored){return new JsonObject();}
    }
    public static String role(ServerPlayer player){
        try {
            String role=grant(player.getUUID()).get("role").getAsString();
            return Set.of("visitor","player","moderator","administrator").contains(role)?role:"visitor";
        } catch(Exception ignored){return "visitor";}
    }
    public static boolean visitor(ServerPlayer player){return role(player).equals("visitor");}
    public static String banReason(UUID id){
        try {JsonObject data=grant(id);return data.has("banned") && data.get("banned").getAsBoolean()?data.get("reason").getAsString():null;}
        catch(Exception ignored){return null;}
    }
    private static void enforce(ServerPlayer player,MinecraftServer server){
        if(!NetworkAccess.allowed(player.connection.getRemoteAddress())){
            player.connection.disconnect(Component.literal("Minecraft-Zugang nur im Heimnetz / Minecraft access is limited to the local network"));return;
        }
        String banned=banReason(player.getUUID());
        if(banned!=null){player.connection.disconnect(Component.literal("Dein Zugang zu diesem Server ist gesperrt. Grund / Your access to this server is blocked. Reason: "+banned));return;}
        String role=role(player);
        boolean operator=false;
        try {operator=role.equals("administrator") && grant(player.getUUID()).get("op").getAsBoolean();}
        catch(Exception ignored){}
        if(!operator && server.getPlayerList().isOp(new NameAndId(player.getUUID(),player.getName().getString())))server.getPlayerList().deop(new NameAndId(player.getUUID(),player.getName().getString()));
        if(role.equals("visitor")){
            RESTRICTED.add(player.getUUID());
            if(!player.isSpectator())player.setGameMode(GameType.SPECTATOR);
        } else {
            if(RESTRICTED.remove(player.getUUID()) || player.isSpectator())player.setGameMode(GameType.SURVIVAL);
            if(operator && !server.getPlayerList().isOp(new NameAndId(player.getUUID(),player.getName().getString())))server.getPlayerList().op(new NameAndId(player.getUUID(),player.getName().getString()));
        }
    }
    private static double now(){return System.currentTimeMillis()/1000.0;}
    private static void flushPlayers(){
        JsonObject players=new JsonObject();JsonArray list=new JsonArray();PLAYERS.values().forEach(list::add);
        players.add("players",list);players.addProperty("at",now());players.addProperty("source","server_guard");
        write(BASE.resolve("reports/players.json"),players);
    }
    private static void audit(String event,ServerPlayer player){
        JsonObject data=new JsonObject();data.addProperty("at",now());data.addProperty("event",event);
        data.addProperty("uuid",player.getUUID().toString());data.addProperty("name",player.getName().getString());
        try {
            Files.createDirectories(BASE.resolve("reports"));
            Files.writeString(BASE.resolve("reports/player-events.jsonl"),new Gson().toJson(data)+"\n",StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(Exception ignored){}
    }
    public static boolean moderation(String action,ServerPlayer player,ServerPlayer target,String detail){
        JsonObject data=new JsonObject();data.addProperty("at",now());data.addProperty("event","player_moderation");
        data.addProperty("uuid",player.getUUID().toString());data.addProperty("name",player.getName().getString());
        data.addProperty("action",action);data.addProperty("detail",detail);data.addProperty("phase","authorized");
        if(target!=null)data.addProperty("target_uuid",target.getUUID().toString());
        try {Files.writeString(BASE.resolve("reports/player-events.jsonl"),new Gson().toJson(data)+"\n",StandardCharsets.UTF_8,
            StandardOpenOption.CREATE,StandardOpenOption.APPEND);return true;}catch(Exception ignored){return false;}
    }
    public static void login(ServerPlayer player,MinecraftServer server){
        enforce(player,server);
        if(closed()){
            player.connection.disconnect(Component.literal("Der Zugang zum Server ist vorübergehend gesperrt. Bitte versuche es später erneut. / Server access is temporarily closed. Please try again later."));return;
        }
        JsonObject info=PLAYERS.computeIfAbsent(player.getUUID(),id->{
            JsonObject o=new JsonObject();o.addProperty("uuid",id.toString());o.addProperty("first_seen",now());o.addProperty("play_seconds",0);return o;
        });
        info.addProperty("name",player.getName().getString());info.addProperty("online_since",now());
        info.addProperty("last_seen",now());info.addProperty("role",role(player));
        audit("player_login",player);
        if(visitor(player))player.sendSystemMessage(Component.literal("Besucher: Du kannst die Welt ansehen. Zum Mitspielen können dich die Server-Admins freigeben. / Visitor: you can explore the world. Ask the server admins to approve you for playing."));
    }
    public static void logout(ServerPlayer player){
        JsonObject info=PLAYERS.get(player.getUUID());
        if(info!=null){
            if(info.has("online_since")){
                double duration=Math.max(0,now()-info.get("online_since").getAsDouble());
                info.addProperty("play_seconds",info.get("play_seconds").getAsDouble()+duration);info.remove("online_since");
            }
            info.addProperty("last_seen",now());
        }
        audit("player_logout",player);
        flushPlayers();
    }
    public static void tick(MinecraftServer server){
        ticks++;
        long clock=System.nanoTime();
        if(clock-windowStart>=5_000_000_000L){actualTps=ticks*1_000_000_000.0/(clock-windowStart);ticks=0;windowStart=clock;}
        long now=System.currentTimeMillis();
        if(now-lastReport<1000)return;lastReport=now;
        if(PLAYERS.isEmpty()){
            JsonObject previous=read(BASE.resolve("reports/players.json"));
            if(previous.has("players"))for(JsonElement value:previous.getAsJsonArray("players")){
                try {
                    JsonObject o=value.getAsJsonObject();
                    if(o.has("online_since")){
                        double observed=Math.max(0,o.get("last_seen").getAsDouble()-o.get("online_since").getAsDouble());
                        o.addProperty("play_seconds",o.get("play_seconds").getAsDouble()+observed);o.remove("online_since");
                    }
                    PLAYERS.put(UUID.fromString(o.get("uuid").getAsString()),o);
                }catch(Exception ignored){}
            }
        }
        for(ServerPlayer player:server.getPlayerList().getPlayers()){
            enforce(player,server);
            JsonObject info=PLAYERS.get(player.getUUID());if(info!=null){info.addProperty("last_seen",now());info.addProperty("role",role(player));}
        }
        RoleCommands.refresh(server);
        JsonObject report=new JsonObject();report.addProperty("at",now());report.addProperty("guard_version",BUILD_VERSION);report.addProperty("guard_protocol",1);
        report.addProperty("online_mode",server.usesAuthentication());report.addProperty("maintenance_closed",closed());
        report.addProperty("players_online",server.getPlayerList().getPlayerCount());
        report.addProperty("tps",Math.min(20,actualTps));report.addProperty("mspt",server.getAverageTickTimeNanos()/1_000_000.0);
        report.addProperty("visitor_client_test","NOT_VERIFIED");
        report.addProperty("permissions_protocol","mcj_roles_v1");
        report.addProperty("network_access_protocol","mcj_network_v1");
        report.addProperty("public_game",NetworkAccess.publicGame());
        report.addProperty("network_access_fingerprint",NetworkAccess.fingerprint());
        write(BASE.resolve("reports/guard-status.json"),report);
        flushPlayers();
    }
}

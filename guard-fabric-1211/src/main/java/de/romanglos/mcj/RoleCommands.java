package de.romanglos.mcj;

import com.google.gson.*;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.exceptions.SimpleCommandExceptionType;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import java.nio.file.*;
import java.util.*;

/** Four explicit abilities. No command text is ever run with elevated permissions. */
public final class RoleCommands {
    private static final Path CONFIG=Path.of("/mcj-control/roles/permissions.json");
    private static final Set<String> ABILITIES=Set.of("kick","announce","time","weather");
    private static final Set<String> ROLES=Set.of("visitor","player","moderator","administrator");
    private static final Map<UUID,String> LAST=new HashMap<>();
    private static final Map<UUID,Long> LAST_ACTION=new HashMap<>();
    private static final SimpleCommandExceptionType DENIED=new SimpleCommandExceptionType(Component.literal("Dir fehlen die Rechte für diesen Befehl. Bitte wende dich an die Server-Admins. / You do not have permission for this command. Please contact the server admins."));

    private static JsonObject configuration(){
        try {
            if(Files.isSymbolicLink(CONFIG) || Files.size(CONFIG)>65536)return new JsonObject();
            JsonObject root=JsonParser.parseString(Files.readString(CONFIG)).getAsJsonObject();
            if(root.get("format").getAsInt()!=1)return new JsonObject();
            JsonObject roles=root.getAsJsonObject("roles");
            if(!roles.keySet().equals(ROLES))return new JsonObject();
            for(String role:ROLES){
                JsonArray values=roles.getAsJsonArray(role);Set<String> seen=new HashSet<>();
                if(values.size()>4 || (role.equals("visitor") && !values.isEmpty()))return new JsonObject();
                for(JsonElement item:values){
                    if(!item.isJsonPrimitive() || !item.getAsJsonPrimitive().isString())return new JsonObject();
                    String ability=item.getAsString();
                    if(!ABILITIES.contains(ability) || !seen.add(ability))return new JsonObject();
                }
            }
            return roles;
        }catch(Exception ignored){return new JsonObject();}
    }
    private static boolean allowed(CommandSourceStack source,String ability){
        if(!(source.getEntity() instanceof ServerPlayer player) || Guard.visitor(player))return false;
        try {
            JsonArray values=configuration().getAsJsonArray(Guard.role(player));
            for(JsonElement value:values)if(value.getAsString().equals(ability))return true;
        }catch(Exception ignored){}
        return false;
    }
    private static ServerPlayer require(CommandSourceStack source,String ability) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        if(!allowed(source,ability))throw DENIED.create();
        ServerPlayer player=(ServerPlayer)source.getEntity();long now=System.nanoTime();
        Long previous=LAST_ACTION.get(player.getUUID());
        if(previous!=null && now-previous<1_000_000_000L)throw DENIED.create();
        LAST_ACTION.put(player.getUUID(),now);return player;
    }
    public static void register(com.mojang.brigadier.CommandDispatcher<CommandSourceStack> dispatcher){
        var root=Commands.literal("mcj").requires(s->ABILITIES.stream().anyMatch(a->allowed(s,a)));
        root.then(Commands.literal("kick").requires(s->allowed(s,"kick"))
            .then(Commands.argument("player",StringArgumentType.word())
            .then(Commands.argument("reason",StringArgumentType.greedyString()).executes(ctx->{
                ServerPlayer actor=require(ctx.getSource(),"kick");
                String name=StringArgumentType.getString(ctx,"player");String reason=StringArgumentType.getString(ctx,"reason");
                if(!name.matches("[A-Za-z0-9_]{1,16}") || reason.isBlank() || reason.length()>150 || reason.indexOf('\n')>=0 || reason.indexOf('\r')>=0)throw DENIED.create();
                ServerPlayer target=ctx.getSource().getServer().getPlayerList().getPlayers().stream()
                    .filter(p->p.getName().getString().equalsIgnoreCase(name)).findFirst().orElse(null);
                if(target==null)throw DENIED.create();
                boolean self=target.getUUID().equals(actor.getUUID());
                if(!self && (Guard.role(target).equals("administrator")
                    || (Guard.role(target).equals("moderator") && !Guard.role(actor).equals("administrator"))))throw DENIED.create();
                if(!Guard.moderation("kick",actor,target,reason))throw DENIED.create();
                target.connection.disconnect(Component.literal("Du wurdest vom Server getrennt. Grund / You were disconnected from the server. Reason: "+reason));return 1;
            }))));
        root.then(Commands.literal("announce").requires(s->allowed(s,"announce"))
            .then(Commands.argument("message",StringArgumentType.greedyString()).executes(ctx->{
                ServerPlayer actor=require(ctx.getSource(),"announce");String message=StringArgumentType.getString(ctx,"message");
                if(message.isBlank() || message.length()>500 || message.indexOf('\n')>=0 || message.indexOf('\r')>=0)throw DENIED.create();
                Component text=Component.literal("["+actor.getName().getString()+"] "+message);
                if(!Guard.moderation("announce",actor,null,message))throw DENIED.create();
                for(ServerPlayer player:ctx.getSource().getServer().getPlayerList().getPlayers())player.sendSystemMessage(text);
                return 1;
            })));
        var clock=Commands.literal("time").requires(s->allowed(s,"time"));
        for(String value:List.of("day","night"))clock.then(Commands.literal(value).executes(ctx->{
            ServerPlayer actor=require(ctx.getSource(),"time");
            if(!Guard.moderation("time",actor,null,value))throw DENIED.create();
            for(var level:ctx.getSource().getServer().getAllLevels())level.setDayTime(value.equals("day")?1000:13000);return 1;
        }));
        root.then(clock);
        var weather=Commands.literal("weather").requires(s->allowed(s,"weather"));
        for(String value:List.of("clear","rain"))weather.then(Commands.literal(value).executes(ctx->{
            ServerPlayer actor=require(ctx.getSource(),"weather");
            if(!Guard.moderation("weather",actor,null,value))throw DENIED.create();
            ctx.getSource().getLevel().setWeatherParameters(value.equals("clear")?6000:0,6000,value.equals("rain"),false);return 1;
        }));
        dispatcher.register(root.then(weather));
    }
    public static void refresh(MinecraftServer server){
        String config=configuration().toString();Set<UUID> online=new HashSet<>();
        for(ServerPlayer player:server.getPlayerList().getPlayers()){
            online.add(player.getUUID());String signature=Guard.role(player)+config;
            if(!signature.equals(LAST.put(player.getUUID(),signature)))server.getCommands().sendCommands(player);
        }
        LAST.keySet().retainAll(online);
        LAST_ACTION.keySet().retainAll(online);
    }
}

package de.romanglos.mcj;
import java.net.InetSocketAddress;
import java.nio.file.*;
public final class NetworkAccessCheck {
    public static void main(String[] args) throws Exception {
        Path directory=Files.createTempDirectory("mcj-network-policy-test-");
        Path policy=directory.resolve("policy.json");int checks=0;
        try {
            if(!NetworkAccess.publicGame(policy))throw new AssertionError("Legacy installation changed");checks++;
            for(String ip:new String[]{"127.0.0.1","::1","10.0.1.2","172.16.0.1","172.31.255.254","192.168.120.10","fd12::1","fc00::1"}){
                if(!NetworkAccess.local(new InetSocketAddress(ip,25565)))throw new AssertionError("Local address rejected: "+ip);checks++;
            }
            for(String ip:new String[]{"198.51.100.7","203.0.113.8","8.8.8.8","172.32.0.1","172.15.0.1","169.254.1.1","fe80::1","2001:db8::1","0.0.0.0","::"}){
                if(NetworkAccess.local(new InetSocketAddress(ip,25565)))throw new AssertionError("Non-local address accepted: "+ip);checks++;
            }
            if(NetworkAccess.local(InetSocketAddress.createUnresolved("unresolved.invalid",25565)))throw new AssertionError("Unresolved address accepted");checks++;
            for(String value:new String[]{"{\"public_game\":false}","{\"public_game\":\"true\"}","{}","broken"}){
                Files.writeString(policy,value);if(NetworkAccess.publicGame(policy))throw new AssertionError("Closed/invalid policy opened access");checks++;
            }
            Files.writeString(policy,"{\"public_game\":true}");if(!NetworkAccess.publicGame(policy))throw new AssertionError("Explicit public access rejected");checks++;
            Files.writeString(policy,"x".repeat(4097));if(NetworkAccess.publicGame(policy))throw new AssertionError("Oversized policy accepted");checks++;
            Files.delete(policy);Files.createSymbolicLink(policy,directory.resolve("missing"));if(NetworkAccess.publicGame(policy))throw new AssertionError("Policy symlink accepted");checks++;
            System.out.println("MCJ network policy checks passed: "+checks);
        }finally{Files.deleteIfExists(policy);Files.delete(directory);}
    }
}

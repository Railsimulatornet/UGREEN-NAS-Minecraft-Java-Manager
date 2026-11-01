package de.romanglos.mcj.createtrains;

/** Two byte-verified variants of Create Adapted 1.31; no wildcard acceptance. */
public final class CreateCompatibility {
    private CreateCompatibility() {}

    public static boolean accepts(String sha256) {
        return "4e8684618edeedae5dbfbe5ec8ba05d57c8c251cb34beb69160f53cbd97b4099".equals(sha256)
            || "9008cd82a9233fdb0ddadb33cd5fb11c9fc26b9ea102ad245319a9aa1b2964c8".equals(sha256);
    }
}

package com.dlxyuki.wms.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import org.bouncycastle.crypto.generators.Argon2BytesGenerator;
import org.bouncycastle.crypto.params.Argon2Parameters;

final class Argon2PhcVerifier {
    private Argon2PhcVerifier() {}

    static boolean matches(String raw, String encoded) {
        try {
            String[] parts = encoded.split("\\$");
            if (parts.length != 6 || !"argon2id".equals(parts[1]) || !"v=19".equals(parts[2])) return false;
            Map<String, Integer> parameters = parameters(parts[3]);
            byte[] salt = decode(parts[4]);
            byte[] expected = decode(parts[5]);
            Argon2Parameters config = new Argon2Parameters.Builder(Argon2Parameters.ARGON2_id)
                .withVersion(Argon2Parameters.ARGON2_VERSION_13)
                .withMemoryAsKB(parameters.get("m"))
                .withIterations(parameters.get("t"))
                .withParallelism(parameters.get("p"))
                .withSalt(salt)
                .build();
            Argon2BytesGenerator generator = new Argon2BytesGenerator();
            generator.init(config);
            byte[] actual = new byte[expected.length];
            generator.generateBytes(raw.getBytes(StandardCharsets.UTF_8), actual);
            return MessageDigest.isEqual(expected, actual);
        } catch (RuntimeException exception) {
            return false;
        }
    }

    private static Map<String, Integer> parameters(String value) {
        Map<String, Integer> result = new HashMap<>();
        for (String item : value.split(",")) {
            String[] pair = item.split("=", 2);
            result.put(pair[0], Integer.parseInt(pair[1]));
        }
        if (!result.keySet().containsAll(java.util.Set.of("m", "t", "p"))) {
            throw new IllegalArgumentException("Incomplete Argon2 parameters");
        }
        return result;
    }

    private static byte[] decode(String value) {
        int padding = (4 - value.length() % 4) % 4;
        return Base64.getDecoder().decode(value + "=".repeat(padding));
    }
}

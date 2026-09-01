package com.dlxyuki.wms.auth;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;

class Argon2PhcVerifierTest {
    @Test
    void verifiesPythonCompatibleArgon2idParameters() {
        Argon2PasswordEncoder encoder = new Argon2PasswordEncoder(16, 32, 4, 65_536, 3);
        String encoded = encoder.encode("compatibility-test-password");

        assertThat(Argon2PhcVerifier.matches("compatibility-test-password", encoded)).isTrue();
        assertThat(Argon2PhcVerifier.matches("wrong-password", encoded)).isFalse();
    }
}

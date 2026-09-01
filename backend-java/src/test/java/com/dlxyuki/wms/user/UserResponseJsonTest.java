package com.dlxyuki.wms.user;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class UserResponseJsonTest {
    @Test void serializesFrontendContractAsSnakeCase() throws Exception {
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        mapper.setPropertyNamingStrategy(com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE);
        UserResponse response = new UserResponse(1, Instant.parse("2026-01-01T00:00:00Z"), Instant.parse("2026-01-01T00:00:00Z"),
            "tester", "Test User", "test@example.com", "VIEWER", true, List.of("dashboard:view"),
            "SELECTED", "ALL", List.of(2L), List.of());
        String content = mapper.writeValueAsString(response);
        assertThat(content).contains("\"display_name\"", "\"warehouse_ids\"")
            .doesNotContain("\"displayName\"");
    }
}

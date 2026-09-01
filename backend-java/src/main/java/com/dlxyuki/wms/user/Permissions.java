package com.dlxyuki.wms.user;

import java.util.List;
import java.util.Map;

public final class Permissions {
    private static final Map<String, List<String>> VALUES = Map.of(
        "ADMIN", List.of("manage_inbound", "manage_outbound", "manage_users", "manage_warehouse", "read"),
        "MANAGER", List.of("manage_inbound", "manage_outbound", "manage_warehouse", "read"),
        "INBOUND", List.of("manage_inbound", "manage_warehouse", "read"),
        "OUTBOUND", List.of("manage_outbound", "read"),
        "WAREHOUSE", List.of("manage_inbound", "manage_outbound", "manage_warehouse", "read"),
        "VIEWER", List.of("read"));
    public static List<String> forRole(String role) { return VALUES.getOrDefault(role, List.of("read")); }
    private Permissions() {}
}

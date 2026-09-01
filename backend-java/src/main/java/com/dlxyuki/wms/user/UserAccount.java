package com.dlxyuki.wms.user;

import java.time.Instant;
import java.util.List;

public record UserAccount(long id, Instant createdAt, Instant updatedAt,
                          String username, String displayName, String email, String passwordHash,
                          String role, boolean active, String warehouseScopeMode, String customerScopeMode,
                          List<Long> warehouseIds, List<Long> customerIds) {}

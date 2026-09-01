package com.dlxyuki.wms.user;

import java.time.Instant;
import java.util.List;

public record UserResponse(long id, Instant createdAt, Instant updatedAt,
                           String username, String displayName, String email, String role, boolean isActive,
                           List<String> permissions, String warehouseScopeMode, String customerScopeMode,
                           List<Long> warehouseIds, List<Long> customerIds) {
    public static UserResponse from(UserAccount user) {
        return new UserResponse(user.id(), user.createdAt(), user.updatedAt(), user.username(), user.displayName(), user.email(), user.role(), user.active(),
            Permissions.forRole(user.role()), user.warehouseScopeMode(), user.customerScopeMode(), user.warehouseIds(), user.customerIds());
    }
}

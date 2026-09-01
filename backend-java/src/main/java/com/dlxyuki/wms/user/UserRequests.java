package com.dlxyuki.wms.user;
import jakarta.validation.constraints.*;
import java.util.List;
public final class UserRequests {
    public record Create(@NotBlank @Size(min=3,max=50) @Pattern(regexp="^[A-Za-z0-9_.-]+$") String username,
        @NotBlank @Size(max=100) String displayName, @NotBlank @Email String email, @NotBlank @Size(min=10,max=128) String password,
        String role, String warehouseScopeMode, String customerScopeMode, List<Long> warehouseIds, List<Long> customerIds) {}
    public record Update(@Size(min=1,max=100) String displayName, @Email String email, @Size(min=10,max=128) String password, String role, Boolean isActive) {}
    public record Scope(String warehouseScopeMode, String customerScopeMode, List<Long> warehouseIds, List<Long> customerIds) {}
    private UserRequests() {}
}

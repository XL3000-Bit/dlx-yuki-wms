package com.dlxyuki.wms.auth;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
    private final AuthService auth;
    public AuthController(AuthService auth) { this.auth = auth; }

    @PostMapping("/login") TokenPair login(@Valid @RequestBody LoginRequest request) { return auth.login(request.username(), request.password()); }
    @PostMapping("/refresh") TokenPair refresh(@Valid @RequestBody RefreshRequest request) { return auth.refresh(request.refreshToken()); }

    public record LoginRequest(@NotBlank String username, @NotBlank String password) {}
    public record RefreshRequest(@NotBlank String refreshToken) {}
}

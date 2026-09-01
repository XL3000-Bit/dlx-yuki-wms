package com.dlxyuki.wms.auth;

import com.dlxyuki.wms.config.AppProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Service;

@Service
public class JwtService {
    private final AppProperties.Jwt settings;
    private final SecretKey key;

    public JwtService(AppProperties properties) {
        this.settings = properties.jwt();
        if (!"HS256".equals(settings.algorithm())) throw new IllegalArgumentException("Only JWT_ALGORITHM=HS256 is supported");
        byte[] bytes = settings.secretKey().getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32) throw new IllegalArgumentException("JWT_SECRET_KEY must be at least 32 bytes");
        this.key = Keys.hmacShaKeyFor(bytes);
    }

    public String access(long userId) { return create(userId, "access", Duration.ofMinutes(settings.accessTokenExpireMinutes())); }
    public String refresh(long userId) { return create(userId, "refresh", Duration.ofDays(settings.refreshTokenExpireDays())); }

    public long subject(String token, String expectedType) {
        Claims claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        if (!expectedType.equals(claims.get("type", String.class))) throw new IllegalArgumentException("Unexpected token type");
        return Long.parseLong(claims.getSubject());
    }

    private String create(long userId, String type, Duration duration) {
        Instant now = Instant.now();
        return Jwts.builder().subject(Long.toString(userId)).claim("type", type).id(UUID.randomUUID().toString())
            .issuedAt(Date.from(now)).expiration(Date.from(now.plus(duration))).signWith(key, Jwts.SIG.HS256).compact();
    }
}

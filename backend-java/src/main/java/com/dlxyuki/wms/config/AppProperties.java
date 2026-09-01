package com.dlxyuki.wms.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("app")
public record AppProperties(String databaseUrl, String businessTimezone, Jwt jwt) {
    public record Jwt(String secretKey, String algorithm, long accessTokenExpireMinutes, long refreshTokenExpireDays) {}
}

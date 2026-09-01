package com.dlxyuki.wms.auth;

public record TokenPair(String accessToken, String refreshToken, String tokenType) {}

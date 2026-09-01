package com.dlxyuki.wms.auth;

public class UnauthorizedException extends RuntimeException {
    public UnauthorizedException(String message) { super(message); }
    static UnauthorizedException badLogin() { return new UnauthorizedException("Incorrect username or password"); }
}

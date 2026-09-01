package com.dlxyuki.wms.config;

import com.dlxyuki.wms.auth.UnauthorizedException;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import jakarta.validation.ConstraintViolationException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(UnauthorizedException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    Map<String, String> unauthorized(UnauthorizedException exception) { return Map.of("detail", exception.getMessage()); }
    @ExceptionHandler(ApiException.class)
    org.springframework.http.ResponseEntity<Map<String, String>> api(ApiException exception) {
        return org.springframework.http.ResponseEntity.status(exception.status()).body(Map.of("detail", exception.getMessage()));
    }
    @ExceptionHandler(MethodArgumentNotValidException.class) @ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)
    Map<String, Object> validation(MethodArgumentNotValidException exception) {
        return Map.of("detail", exception.getBindingResult().getFieldErrors().stream().map(error -> Map.of("loc", java.util.List.of("body", error.getField()), "msg", error.getDefaultMessage(), "type", "value_error")).toList());
    }
    @ExceptionHandler({ConstraintViolationException.class, HandlerMethodValidationException.class, MethodArgumentTypeMismatchException.class})
    @ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)
    Map<String, Object> queryValidation(Exception exception) {
        return Map.of("detail", java.util.List.of(Map.of("loc", java.util.List.of("query"), "msg", "Invalid query parameter", "type", "value_error")));
    }
    @ExceptionHandler(DataIntegrityViolationException.class) @ResponseStatus(HttpStatus.CONFLICT)
    Map<String, String> conflict(DataIntegrityViolationException exception) { return Map.of("detail", "Duplicate or invalid reference"); }
}

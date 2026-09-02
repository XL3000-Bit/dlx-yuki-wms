package com.yuki.wms.v2.observability;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component("v2RequestContextFilter")
public class RequestContextFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String requestId = request.getHeader("X-Request-ID");
        if (requestId == null || requestId.isBlank()) requestId = UUID.randomUUID().toString();
        response.setHeader("X-Request-ID", requestId);
        try {
            MDC.put("request_id", requestId);
            Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
            if (authentication != null && authentication.getPrincipal() instanceof UserAccount user) {
                MDC.put("user_id", Long.toString(user.id()));
                MDC.put("username", user.username());
                MDC.put("role", user.role());
            }
            chain.doFilter(request, response);
        } finally {
            MDC.clear();
        }
    }
}

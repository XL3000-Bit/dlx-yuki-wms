package com.dlxyuki.wms.auth;

import com.dlxyuki.wms.user.UserAccount;
import com.dlxyuki.wms.user.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class BearerTokenFilter extends OncePerRequestFilter {
    private final JwtService jwt;
    private final UserRepository users;
    public BearerTokenFilter(JwtService jwt, UserRepository users) { this.jwt = jwt; this.users = users; }

    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) { chain.doFilter(request, response); return; }
        try {
            long id = jwt.subject(header.substring(7), "access");
            UserAccount user = users.findById(id).filter(UserAccount::active).orElseThrow();
            SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(user, null, java.util.List.of()));
        } catch (Exception exception) {
            SecurityContextHolder.clearContext();
            response.setStatus(401); response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"detail\":\"Invalid credentials\"}");
            return;
        }
        chain.doFilter(request, response);
    }
}

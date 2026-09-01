package com.dlxyuki.wms.auth;

import com.dlxyuki.wms.user.UserAccount;
import com.dlxyuki.wms.user.UserRepository;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {
    private final UserRepository users;
    private final JwtService jwt;
    private final Argon2PasswordEncoder argon2 = Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
    private final BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder();

    public AuthService(UserRepository users, JwtService jwt) { this.users = users; this.jwt = jwt; }

    public TokenPair login(String username, String password) {
        UserAccount user = users.findByUsernameOrEmail(username).orElseThrow(UnauthorizedException::badLogin);
        if (!user.active() || !matches(password, user.passwordHash())) throw UnauthorizedException.badLogin();
        return tokens(user.id());
    }

    public TokenPair refresh(String token) {
        try {
            long id = jwt.subject(token, "refresh");
            UserAccount user = users.findById(id).orElseThrow(() -> new UnauthorizedException("Inactive or missing user"));
            if (!user.active()) throw new UnauthorizedException("Inactive or missing user");
            return tokens(id);
        } catch (UnauthorizedException exception) { throw exception; }
        catch (Exception exception) { throw new UnauthorizedException("Invalid refresh token"); }
    }

    private TokenPair tokens(long id) { return new TokenPair(jwt.access(id), jwt.refresh(id), "bearer"); }
    public String hashPassword(String raw) { return argon2.encode(raw); }

    private boolean matches(String raw, String encoded) {
        if (encoded == null) return false;
        if (encoded.startsWith("$argon2")) return Argon2PhcVerifier.matches(raw, encoded);
        if (encoded.startsWith("$2")) return bcrypt.matches(raw, encoded);
        return false;
    }
}

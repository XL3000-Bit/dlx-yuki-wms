package com.dlxyuki.wms.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.auth.AuthService;
import com.dlxyuki.wms.config.ApiException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;

class UsersReadContractTest {
    private static UserAccount user(long id, String role) {
        return new UserAccount(id, Instant.parse("2026-01-01T00:00:00Z"), Instant.parse("2026-01-01T00:00:00Z"),
            "user" + id, "User " + id, "user" + id + "@example.com", "hash", role, true,
            "SELECTED", "ALL", List.of(7L), List.of());
    }

    @Test void exposesOnlyTheTwoFastApiGetShapes() {
        List<String> paths = Arrays.stream(UserController.class.getDeclaredMethods())
            .filter(method -> method.isAnnotationPresent(GetMapping.class))
            .map(method -> method.getAnnotation(GetMapping.class))
            .flatMap(mapping -> mapping.value().length == 0 ? java.util.stream.Stream.of("") : Arrays.stream(mapping.value()))
            .sorted().toList();
        assertThat(paths).containsExactly("", "/me");
    }

    @Test void listsUsersForAdminsAndKeepsTheSnakeCaseReadShape() throws Exception {
        UserRepository repository = mock(UserRepository.class);
        UserAccount admin = user(1, "ADMIN");
        when(repository.findAll()).thenReturn(List.of(user(2, "VIEWER")));
        UserManagementService service = new UserManagementService(repository, mock(AuthService.class));
        UserController controller = new UserController(service);

        assertThat(controller.list(admin)).hasSize(1);
        String json = new ObjectMapper().findAndRegisterModules()
            .setPropertyNamingStrategy(com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE)
            .writeValueAsString(controller.me(admin));
        assertThat(json).contains("\"display_name\"", "\"permissions\"", "\"warehouse_ids\"", "\"customer_ids\"")
            .doesNotContain("displayName");
    }

    @Test void rejectsTheAdminListForNonAdmins() {
        UserManagementService service = new UserManagementService(mock(UserRepository.class), mock(AuthService.class));
        UserController controller = new UserController(service);
        assertThatThrownBy(() -> controller.list(user(2, "VIEWER")))
            .isInstanceOfSatisfying(ApiException.class, error -> {
                assertThat(error.status()).isEqualTo(HttpStatus.FORBIDDEN);
                assertThat(error.getMessage()).isEqualTo("Admin permission required");
            });
    }
}

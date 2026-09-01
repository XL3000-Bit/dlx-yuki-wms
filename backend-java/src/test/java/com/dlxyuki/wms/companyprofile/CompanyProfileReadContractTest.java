package com.dlxyuki.wms.companyprofile;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.lang.reflect.Method;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class CompanyProfileReadContractTest {
    @Test void exposesTheSingleFastApiGetRoute() {
        assertThat(CompanyProfileController.class.getAnnotation(RequestMapping.class).value())
            .containsExactly("/api/v1/company-profile");
        Method read = java.util.Arrays.stream(CompanyProfileController.class.getDeclaredMethods())
            .filter(method -> method.getName().equals("read")).findFirst().orElseThrow();
        assertThat(read.isAnnotationPresent(GetMapping.class)).isTrue();
    }

    @Test void returnsTheExistingSnakeCaseProfileWithoutWriting() {
        CompanyProfileRepository repository = mock(CompanyProfileRepository.class);
        Map<String,Object> row = Map.of("id", 1L, "company_name", "DLX", "default_warehouse_id", 7L);
        when(repository.first()).thenReturn(Optional.of(row));
        CompanyProfileController controller = new CompanyProfileController(repository);
        assertThat(controller.read(mock(UserAccount.class))).isEqualTo(row);
    }

    @Test void doesNotCreateAProfileDuringARead() {
        CompanyProfileRepository repository = mock(CompanyProfileRepository.class);
        when(repository.first()).thenReturn(Optional.empty());
        CompanyProfileController controller = new CompanyProfileController(repository);
        assertThatThrownBy(() -> controller.read(mock(UserAccount.class)))
            .isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.status()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE));
    }
}

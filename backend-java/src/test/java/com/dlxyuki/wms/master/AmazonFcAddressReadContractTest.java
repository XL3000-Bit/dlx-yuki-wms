package com.dlxyuki.wms.master;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.config.ApiException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;

class AmazonFcAddressReadContractTest {
    @Test void exposesTheFastApiDynamicFcAddressRoute() {
        Method method = Arrays.stream(MasterDataController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals("fc")).findFirst().orElseThrow();
        assertThat(method.getAnnotation(GetMapping.class).value())
            .containsExactly("/amazon-fc-addresses/{code}");
    }

    @Test void returnsTheSnakeCaseFcRecordAndUsesNotFoundForMissingCodes() {
        MasterDataRepository repository = mock(MasterDataRepository.class);
        when(repository.fc("lax9")).thenReturn(Optional.of(Map.of("fc_code", "LAX9")));
        when(repository.fc("missing")).thenReturn(Optional.empty());
        MasterDataController controller = new MasterDataController(repository);

        assertThat(controller.fc("lax9")).containsEntry("fc_code", "LAX9");
        assertThatThrownBy(() -> controller.fc("missing"))
            .isInstanceOfSatisfying(ApiException.class, error -> {
                assertThat(error.status()).isEqualTo(HttpStatus.NOT_FOUND);
                assertThat(error.getMessage()).isEqualTo("Amazon FC not found");
            });
    }
}

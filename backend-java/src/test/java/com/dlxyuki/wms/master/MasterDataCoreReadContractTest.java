package com.dlxyuki.wms.master;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.user.UserAccount;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class MasterDataCoreReadContractTest {
    @Test void exposesTheFirstThreeFastApiMasterReadRoutes() {
        assertThat(MasterDataController.class.getAnnotation(RequestMapping.class).value())
            .containsExactly("/api/v1/master-data");
        assertThat(getPath("customers")).containsExactly("/customers");
        assertThat(getPath("warehouses")).containsExactly("/warehouses");
        assertThat(getPath("areas")).containsExactly("/warehouse-areas");
    }

    @Test void passesTheAuthenticatedUserIntoEveryScopedLookup() {
        MasterDataRepository repository = mock(MasterDataRepository.class);
        UserAccount user = mock(UserAccount.class);
        when(repository.customers(user)).thenReturn(List.of(Map.of("customer_code", "C1")));
        when(repository.warehouses(user)).thenReturn(List.of(Map.of("warehouse_code", "W1")));
        when(repository.areas(user)).thenReturn(List.of(Map.of("area_code", "A1")));
        MasterDataController controller = new MasterDataController(repository);

        assertThat(controller.customers(user).getFirst()).containsEntry("customer_code", "C1");
        assertThat(controller.warehouses(user).getFirst()).containsEntry("warehouse_code", "W1");
        assertThat(controller.areas(user).getFirst()).containsEntry("area_code", "A1");
        verify(repository).customers(user);
        verify(repository).warehouses(user);
        verify(repository).areas(user);
    }

    private String[] getPath(String methodName) {
        Method method = Arrays.stream(MasterDataController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals(methodName)).findFirst().orElseThrow();
        return method.getAnnotation(GetMapping.class).value();
    }
}

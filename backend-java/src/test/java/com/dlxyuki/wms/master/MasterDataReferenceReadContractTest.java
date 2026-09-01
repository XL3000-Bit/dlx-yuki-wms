package com.dlxyuki.wms.master;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.user.UserAccount;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

class MasterDataReferenceReadContractTest {
    @Test void exposesTheThreeStaticFastApiReferenceRoutes() {
        assertThat(getPath("locations")).containsExactly("/warehouse-locations");
        assertThat(getPath("carriers")).containsExactly("/carriers");
        assertThat(getPath("fcs")).containsExactly("/amazon-fc-addresses");
    }

    @Test void locationCodeIsOptionalAndTheWarehouseScopeIsPreserved() {
        Method method = method("locations");
        Parameter query = method.getParameters()[1];
        RequestParam requestParam = query.getAnnotation(RequestParam.class);
        assertThat(requestParam.name()).isEqualTo("location_code");
        assertThat(requestParam.required()).isFalse();

        MasterDataRepository repository = mock(MasterDataRepository.class);
        UserAccount user = mock(UserAccount.class);
        when(repository.locations(user, "A-01")).thenReturn(List.of(Map.of("location_code", "A-01")));
        MasterDataController controller = new MasterDataController(repository);
        assertThat(controller.locations(user, "A-01").getFirst())
            .containsEntry("location_code", "A-01");
        verify(repository).locations(user, "A-01");
    }

    @Test void carrierAndFcListsRemainPlainSnakeCaseArrays() {
        MasterDataRepository repository = mock(MasterDataRepository.class);
        when(repository.carriers()).thenReturn(List.of(Map.of("carrier_code", "UPS")));
        when(repository.fcs()).thenReturn(List.of(Map.of("fc_code", "LAX9")));
        MasterDataController controller = new MasterDataController(repository);

        assertThat(controller.carriers().getFirst()).containsEntry("carrier_code", "UPS");
        assertThat(controller.fcs().getFirst()).containsEntry("fc_code", "LAX9");
    }

    private Method method(String name) {
        return Arrays.stream(MasterDataController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals(name)).findFirst().orElseThrow();
    }

    private String[] getPath(String name) {
        return method(name).getAnnotation(GetMapping.class).value();
    }
}

package com.dlxyuki.wms.dashboard;

import static org.assertj.core.api.Assertions.assertThat;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;

class DashboardReadParityContractTest {
    @Test void dashboardSurfaceRemainsOneReadOnlyOperationsRoute() {
        var methods=Arrays.stream(OperationsDashboardController.class.getDeclaredMethods()).toList();
        assertThat(methods.stream().filter(m->m.isAnnotationPresent(GetMapping.class)).map(m->Arrays.asList(m.getAnnotation(GetMapping.class).value()))).containsExactly(java.util.List.of("/operations"));
        assertThat(methods.stream().filter(m->m.isAnnotationPresent(PostMapping.class))).isEmpty();
    }
}

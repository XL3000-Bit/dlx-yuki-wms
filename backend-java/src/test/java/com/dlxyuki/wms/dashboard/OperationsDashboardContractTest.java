package com.dlxyuki.wms.dashboard;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

class OperationsDashboardContractTest {
    @Test void exposesTheFastApiOperationsRouteAndSnakeCaseQueries() {
        RequestMapping root = OperationsDashboardController.class.getAnnotation(RequestMapping.class);
        assertThat(root.value()).containsExactly("/api/v1/dashboard");
        Method endpoint = Arrays.stream(OperationsDashboardController.class.getDeclaredMethods())
            .filter(method -> method.isAnnotationPresent(GetMapping.class)).findFirst().orElseThrow();
        assertThat(endpoint.getAnnotation(GetMapping.class).value()).containsExactly("/operations");
        assertThat(Arrays.stream(endpoint.getParameters()).map(parameter -> parameter.getAnnotation(RequestParam.class))
            .filter(annotation -> annotation != null).map(RequestParam::name))
            .containsExactly("date_from", "date_to", "warehouse_id");
    }
}

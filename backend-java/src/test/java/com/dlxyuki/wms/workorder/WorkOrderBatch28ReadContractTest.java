package com.dlxyuki.wms.workorder;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class WorkOrderBatch28ReadContractTest {
    @Test
    void exposesOnlyListDetailAndEventsAsGetRoutes() {
        assertThat(WorkOrderController.class.getAnnotation(RequestMapping.class).value())
                .containsExactly("/api/v1/work-orders");
        assertThat(path("list")).isEmpty();
        assertThat(path("detail")).containsExactly("/{work_order_id}");
        assertThat(path("events")).containsExactly("/{work_order_id}/events");
        assertThat(Arrays.stream(WorkOrderController.class.getDeclaredMethods())
                .filter(method -> method.isAnnotationPresent(GetMapping.class)))
                .hasSize(3);
    }

    private String[] path(String methodName) {
        Method method = Arrays.stream(WorkOrderController.class.getDeclaredMethods())
                .filter(candidate -> candidate.getName().equals(methodName))
                .findFirst()
                .orElseThrow();
        return method.getAnnotation(GetMapping.class).value();
    }
}

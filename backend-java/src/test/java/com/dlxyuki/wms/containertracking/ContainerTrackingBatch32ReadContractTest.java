package com.dlxyuki.wms.containertracking;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class ContainerTrackingBatch32ReadContractTest {
    @Test
    void batch32KeepsExactlyTheTwoFastApiGetRoutes() {
        assertThat(ContainerTrackingController.class.getAnnotation(RequestMapping.class).value())
                .containsExactly("/api/v1/container-tracking");
        assertThat(path("list")).isEmpty();
        assertThat(path("detail")).containsExactly("/{tracking_id}");
        assertThat(Arrays.stream(ContainerTrackingController.class.getDeclaredMethods())
                .filter(method -> method.isAnnotationPresent(GetMapping.class)))
                .hasSize(2);
    }

    @Test
    void listContractRetainsPaginationScopeAndDispatchFilters() {
        assertThat(Arrays.stream(ContainerTrackingQuery.class.getRecordComponents())
                .map(component -> component.getName()))
                .containsExactly(
                        "page", "perPage", "q", "status", "warehouseId", "outboundWindow",
                        "outboundFrom", "outboundTo", "dispatchPriority", "sortBy", "sortOrder");
    }

    private String[] path(String methodName) {
        Method method = Arrays.stream(ContainerTrackingController.class.getDeclaredMethods())
                .filter(candidate -> candidate.getName().equals(methodName))
                .findFirst()
                .orElseThrow();
        return method.getAnnotation(GetMapping.class).value();
    }
}

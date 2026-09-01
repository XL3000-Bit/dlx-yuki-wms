package com.dlxyuki.wms.workorder;

import static org.assertj.core.api.Assertions.assertThat;
import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class WorkOrderReadContractTest {
    @Test void exposesOnlyTheThreeReadRoutes(){assertThat(WorkOrderController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/work-orders");assertThat(path("list")).isEmpty();assertThat(path("detail")).containsExactly("/{work_order_id}");assertThat(path("events")).containsExactly("/{work_order_id}/events");assertThat(Arrays.stream(WorkOrderController.class.getDeclaredMethods()).filter(m->m.isAnnotationPresent(GetMapping.class))).hasSize(3);}
    private String[] path(String name){Method m=Arrays.stream(WorkOrderController.class.getDeclaredMethods()).filter(x->x.getName().equals(name)).findFirst().orElseThrow();return m.getAnnotation(GetMapping.class).value();}
}

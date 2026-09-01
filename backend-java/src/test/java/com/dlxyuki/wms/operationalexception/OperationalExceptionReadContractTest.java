package com.dlxyuki.wms.operationalexception;

import static org.assertj.core.api.Assertions.assertThat;
import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class OperationalExceptionReadContractTest {
    @Test void exposesOnlyListDetailAndEvents(){assertThat(OperationalExceptionController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/operational-exceptions");assertThat(path("list")).isEmpty();assertThat(path("detail")).containsExactly("/{exception_id}");assertThat(path("events")).containsExactly("/{exception_id}/events");assertThat(Arrays.stream(OperationalExceptionController.class.getDeclaredMethods()).filter(m->m.isAnnotationPresent(GetMapping.class))).hasSize(3);}
    private String[] path(String name){Method m=Arrays.stream(OperationalExceptionController.class.getDeclaredMethods()).filter(x->x.getName().equals(name)).findFirst().orElseThrow();return m.getAnnotation(GetMapping.class).value();}
}

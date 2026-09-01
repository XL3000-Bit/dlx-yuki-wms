package com.dlxyuki.wms.document;

import static org.assertj.core.api.Assertions.assertThat;
import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class OperationalDocumentReadContractTest {
    @Test void exposesOnlyListDetailAndEvents(){assertThat(OperationalDocumentController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/documents");assertThat(path("list")).isEmpty();assertThat(path("detail")).containsExactly("/{document_id}");assertThat(path("events")).containsExactly("/{document_id}/events");assertThat(Arrays.stream(OperationalDocumentController.class.getDeclaredMethods()).filter(m->m.isAnnotationPresent(GetMapping.class))).hasSize(3);}
    private String[] path(String name){Method m=Arrays.stream(OperationalDocumentController.class.getDeclaredMethods()).filter(x->x.getName().equals(name)).findFirst().orElseThrow();return m.getAnnotation(GetMapping.class).value();}
}

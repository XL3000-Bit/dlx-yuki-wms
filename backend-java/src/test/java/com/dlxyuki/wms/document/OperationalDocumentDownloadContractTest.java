package com.dlxyuki.wms.document;

import static org.assertj.core.api.Assertions.assertThat;
import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class OperationalDocumentDownloadContractTest {
    @Test void exposesOnlyScopedDownloadGet() {
        assertThat(OperationalDocumentDownloadController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/documents");
        Method method=Arrays.stream(OperationalDocumentDownloadController.class.getDeclaredMethods()).filter(m->m.isAnnotationPresent(GetMapping.class)).findFirst().orElseThrow();
        assertThat(method.getAnnotation(GetMapping.class).value()).containsExactly("/{document_id}/download");
        assertThat(Arrays.stream(OperationalDocumentDownloadController.class.getDeclaredMethods()).filter(m->m.isAnnotationPresent(PostMapping.class))).isEmpty();
    }
}

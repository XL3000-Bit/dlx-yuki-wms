package com.dlxyuki.wms.load;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class LoadBatch27ReadContractTest {
    @Test
    void keepsTheBatch27SurfaceReadOnlyAndUnderThePluralPath() {
        assertThat(LoadController.class.getAnnotation(RequestMapping.class).value())
                .containsExactly("/api/v1/loads");
        assertThat(getPath("list")).isEmpty();
        assertThat(getPath("detail")).containsExactly("/{load_id}");
        assertThat(getPath("executionSummary")).containsExactly("/{load_id}/execution-summary");
        assertThat(Arrays.stream(LoadController.class.getDeclaredMethods())
                .filter(method -> method.isAnnotationPresent(GetMapping.class)))
                .hasSize(3);
    }

    private String[] getPath(String methodName) {
        Method method = Arrays.stream(LoadController.class.getDeclaredMethods())
                .filter(candidate -> candidate.getName().equals(methodName))
                .findFirst()
                .orElseThrow();
        return method.getAnnotation(GetMapping.class).value();
    }
}

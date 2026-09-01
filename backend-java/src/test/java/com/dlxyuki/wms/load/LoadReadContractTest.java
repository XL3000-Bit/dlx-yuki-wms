package com.dlxyuki.wms.load;

import static org.assertj.core.api.Assertions.assertThat;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class LoadReadContractTest {
    @Test void exposesOnlyTheThreeReadRoutes(){assertThat(LoadController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/loads");assertThat(path("list")).isEmpty();assertThat(path("detail")).containsExactly("/{load_id}");assertThat(path("executionSummary")).containsExactly("/{load_id}/execution-summary");assertThat(Arrays.stream(LoadController.class.getDeclaredMethods()).filter(m->m.isAnnotationPresent(GetMapping.class))).hasSize(3);}
    @Test void quantitiesAreStrings()throws Exception{var j=new ObjectMapper().readTree(new ObjectMapper().writeValueAsString(Map.of("staged_quantity","12.50")));assertThat(j.get("staged_quantity").isTextual()).isTrue();}
    private String[] path(String name){Method m=Arrays.stream(LoadController.class.getDeclaredMethods()).filter(x->x.getName().equals(name)).findFirst().orElseThrow();return m.getAnnotation(GetMapping.class).value();}
}

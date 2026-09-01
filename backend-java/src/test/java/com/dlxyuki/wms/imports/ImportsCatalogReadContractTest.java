package com.dlxyuki.wms.imports;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.lang.reflect.Method;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

class ImportsCatalogReadContractTest {
    @Test void exposesTheThreeCatalogGetRoutes() {
        assertThat(ImportReadController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/imports");
        Map<String,String[]> paths=new HashMap<>();
        for(Method method:ImportReadController.class.getDeclaredMethods())if(method.isAnnotationPresent(GetMapping.class))
            paths.put(method.getName(),method.getAnnotation(GetMapping.class).value());
        assertThat(paths).containsKeys("profiles","jobs","job");
        assertThat(paths.get("profiles")).containsExactly("/profiles");
        assertThat(paths.get("jobs")).isEmpty();
        assertThat(paths.get("job")).containsExactly("/{jobId}");
    }
    @Test void profilesMatchFastApiOrderAndValues() {
        ImportReadController controller=new ImportReadController(mock(ImportReadRepository.class));
        var values=controller.profiles(mock(UserAccount.class));
        assertThat(values).extracting(ImportReadController.Profile::code)
            .containsExactly("WEST_COAST_4_0_OL","WEST_COAST_4_0_DS","WEST_COAST_4_0_OUTBOUND");
        assertThat(values.get(2).sheetName()).isEqualTo("出库");
    }
    @Test void missingJobIs404() {
        ImportReadRepository repository=mock(ImportReadRepository.class);
        when(repository.find(99)).thenReturn(Optional.empty());
        assertThatThrownBy(()->new ImportReadController(repository).job(99,mock(UserAccount.class)))
            .isInstanceOfSatisfying(ApiException.class,e->assertThat(e.status()).isEqualTo(HttpStatus.NOT_FOUND));
    }
    @Test void statusNameMatchesPydanticComputedField(){assertThat(ImportReadRepository.title("VALIDATION_FAILED")).isEqualTo("Validation Failed");}
}

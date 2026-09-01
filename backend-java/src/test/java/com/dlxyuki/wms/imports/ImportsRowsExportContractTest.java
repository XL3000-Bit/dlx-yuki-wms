package com.dlxyuki.wms.imports;

import static org.assertj.core.api.Assertions.assertThat;
import java.lang.reflect.Method;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;

class ImportsRowsExportContractTest {
    @Test void exposesRowsAndErrorWorkbookRoutes() throws Exception {
        Map<String,String> routes=new HashMap<>();
        for(Method method:ImportReadController.class.getDeclaredMethods())if(method.isAnnotationPresent(GetMapping.class)){
            String[] values=method.getAnnotation(GetMapping.class).value();
            if(values.length>0)routes.put(method.getName(),values[0]);
        }
        assertThat(routes).containsEntry("rows","/{jobId}/rows").containsEntry("errorExport","/{jobId}/errors.xlsx");
        assertThat(ImportReadController.class.getDeclaredMethod("errorExport",long.class,com.dlxyuki.wms.user.UserAccount.class).getReturnType())
            .isEqualTo(ResponseEntity.class);
    }
}

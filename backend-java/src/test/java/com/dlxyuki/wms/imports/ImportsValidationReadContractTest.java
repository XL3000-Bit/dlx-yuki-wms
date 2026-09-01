package com.dlxyuki.wms.imports;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.lang.reflect.Method;
import java.time.OffsetDateTime;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;

class ImportsValidationReadContractTest {
    private static ImportJobResponse job(String status){return new ImportJobResponse(
        7,"INBOUND","a.xlsx","a.xlsx",status,10,4,40d,"VALIDATING",3,1,0,0,1,
        OffsetDateTime.now(),null,null,null,null,null,
        Map.of("validation_seconds",2.5),null,"Validating");}
    @Test void exposesTheThreeValidationGetRoutes(){
        Map<String,String> routes=new HashMap<>();
        for(Method m:ImportReadController.class.getDeclaredMethods())if(m.isAnnotationPresent(GetMapping.class)&&Set.of("progress","validationResult","errors").contains(m.getName()))routes.put(m.getName(),m.getAnnotation(GetMapping.class).value()[0]);
        assertThat(routes).containsEntry("progress","/{jobId}/progress").containsEntry("validationResult","/{jobId}/validation-result").containsEntry("errors","/{jobId}/errors");
    }
    @Test void progressUsesSnakeCaseContract(){ImportReadRepository r=mock();when(r.find(7)).thenReturn(Optional.of(job("VALIDATING")));assertThat(new ImportReadController(r).progress(7,mock(UserAccount.class))).containsEntry("job_id",7L).containsEntry("progress_percent",40d);}
    @Test void incompleteValidationIs409(){ImportReadRepository r=mock();when(r.find(7)).thenReturn(Optional.of(job("VALIDATING")));assertThatThrownBy(()->new ImportReadController(r).validationResult(7,mock(UserAccount.class))).isInstanceOfSatisfying(ApiException.class,e->assertThat(e.status()).isEqualTo(HttpStatus.CONFLICT));}
    @Test void validationIssuesFollowRows(){ImportReadRepository r=mock();when(r.find(7)).thenReturn(Optional.of(job("READY")));when(r.rowsForValidation(7)).thenReturn(List.of(new LinkedHashMap<>(Map.of("row_number",2,"data",Map.of(),"status","ERROR"))));Map<String,Object> error=new LinkedHashMap<>();error.put("row_number",2);error.put("severity","ERROR");error.put("column_name",null);error.put("error_code","BAD");error.put("error_message","Bad row");when(r.errors(7)).thenReturn(List.of(error));var result=new ImportReadController(r).validationResult(7,mock(UserAccount.class));assertThat((List<?>)result.get("rows")).hasSize(1);}
}

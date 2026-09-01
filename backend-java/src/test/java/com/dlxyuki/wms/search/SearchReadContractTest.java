package com.dlxyuki.wms.search;

import static org.assertj.core.api.Assertions.assertThat;
import com.dlxyuki.wms.user.UserAccount;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class SearchReadContractTest {
    @Test void routeAndEntityOrderMatchFastApi() throws Exception {
        assertThat(SearchController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/search");
        Method method=SearchController.class.getDeclaredMethod("search",String.class,int.class,UserAccount.class);
        assertThat(method.getAnnotation(GetMapping.class)).isNotNull();
        assertThat(SearchRepository.TYPES).containsExactly("CONTAINER","OUTBOUND","FBA","PICKING","BOL","LOAD","WORK_ORDER","EXCEPTION","DOCUMENT");
    }
}

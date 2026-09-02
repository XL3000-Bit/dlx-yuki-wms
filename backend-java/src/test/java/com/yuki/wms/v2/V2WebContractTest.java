package com.yuki.wms.v2;

import com.dlxyuki.wms.WmsApplication;
import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = WmsApplication.class)
@AutoConfigureMockMvc
class V2WebContractTest {
    @Autowired MockMvc mvc;

    @Test void applicationContextLoadsAndHealthIsPublic() throws Exception {
        mvc.perform(get("/api/v2/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status", is("ok")))
            .andExpect(jsonPath("$.mode", is("read-only")));
    }

    @Test void invalidJwtUsesFastApiCompatibleError() throws Exception {
        mvc.perform(get("/api/v2/customers").header("Authorization", "Bearer not-a-jwt"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.detail", is("Invalid credentials")));
    }

    @Test void missingJwtUsesFastApiCompatibleError() throws Exception {
        mvc.perform(get("/api/v2/customers"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.detail", is("Not authenticated")));
    }
}

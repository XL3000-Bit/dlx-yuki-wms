package com.dlxyuki.wms.system;

import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HealthControllerTest {
    @Autowired MockMvc mvc;

    @Test void reportsExpectedHealth() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk())
            .andExpect(jsonPath("$.status", is("ok")))
            .andExpect(jsonPath("$.service", is("DLX Yuki WMS V3")));
    }

    @Test void masterDataRequiresBearerToken() throws Exception {
        mvc.perform(get("/api/v1/master-data/customers"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.detail", is("Not authenticated")));
    }
}

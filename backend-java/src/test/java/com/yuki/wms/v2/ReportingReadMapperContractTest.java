package com.yuki.wms.v2;

import static org.assertj.core.api.Assertions.assertThat;

import com.dlxyuki.wms.WmsApplication;
import java.nio.charset.StandardCharsets;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(classes = WmsApplication.class)
class ReportingReadMapperContractTest {
    @Autowired SqlSessionFactory sqlSessionFactory;

    @Test void mapperExposesExpectedReadQueriesOnly() throws Exception {
        try (var stream = getClass().getResourceAsStream("/mapper/ReportingReadMapper.xml")) {
            assertThat(stream).isNotNull();
            String xml = new String(stream.readAllBytes(), StandardCharsets.UTF_8).toLowerCase();
            assertThat(xml).contains("id=\"findcustomers\"", "id=\"findwarehouses\"",
                "id=\"findcarriers\"", "id=\"findfcaddresses\"",
                "id=\"inboundsummary\"", "id=\"inventorysummary\"", "id=\"outboundsummary\"");
            assertThat(xml).doesNotContain("<insert", "<update", "<delete",
                " create ", " alter ", " drop ", " truncate ");
        }

        String namespace = "com.yuki.wms.v2.mapper.ReportingReadMapper.";
        for (String statement : new String[] {"ping", "findCustomers", "findWarehouses", "findCarriers",
                "findFcAddresses", "inboundSummary", "inventorySummary", "outboundSummary"}) {
            assertThat(sqlSessionFactory.getConfiguration().hasStatement(namespace + statement, false)).isTrue();
        }
    }
}

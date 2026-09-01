package com.dlxyuki.wms.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;

class InboundResponseJsonTest {
    @Test void serializesFastApiSnakeCaseContract() throws Exception {
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        InboundResponse value = new InboundResponse(1,"IB2609010001","MSCU1",null,
            new InboundResponse.NamedRef(2,"LAX","Los Angeles"),null, LocalDate.of(2026,9,1),null,
            "LAX9",null,"1.00","2.00",null,null,0,"Pending",0,null,
            new InboundResponse.UserRef(3,"DLX User"), OffsetDateTime.parse("2026-09-01T10:00:00Z"),OffsetDateTime.parse("2026-09-01T10:00:00Z"),false,null);
        String json = mapper.writeValueAsString(value);
        assertThat(json).contains("\"inbound_no\"", "\"container_number\"", "\"status_name\"", "\"aging_days\"", "\"created_by\"", "\"inventory_created\"");
        assertThat(json).contains("\"pallet_qty\":\"1.00\"");
    }
}

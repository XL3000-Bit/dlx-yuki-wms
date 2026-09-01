package com.dlxyuki.wms.inventory;

import static org.assertj.core.api.Assertions.assertThat;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.time.*;
import org.junit.jupiter.api.Test;

class InventoryResponseJsonTest {
    @Test void serializesSnakeCaseAndDecimalQuantitiesAsStrings() throws Exception {
        ObjectMapper mapper = JsonMapper.builder().addModule(new JavaTimeModule())
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE).build();
        InventoryResponse value = new InventoryResponse(1,"LOT1","CONT1",null,null,null,
            new InventoryResponse.NamedRef(2,"WH","Warehouse"),null,3,LocalDate.of(2026,1,1),10,"GREEN","Normal",
            "1.00","1.00","0.00","0.00","2.00","2.00","0.00","0.00","3.00","3.00","0.00","4.0000","4.0000","0.0000",
            0,"Available",null,OffsetDateTime.parse("2026-01-01T00:00:00Z"),OffsetDateTime.parse("2026-01-01T00:00:00Z"));
        JsonNode json = mapper.readTree(mapper.writeValueAsString(value));
        assertThat(json.get("available_pallet_qty").asText()).isEqualTo("1.00");
        assertThat(json.get("source_inbound_id").asLong()).isEqualTo(3);
        assertThat(json.has("availablePalletQty")).isFalse();
    }
}

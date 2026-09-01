package com.dlxyuki.wms.inbound;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class InboundReadContractTest {
    @Test void exposesOnlyTheTwoSingularFastApiReadRoutes() {
        assertThat(InboundController.class.getAnnotation(RequestMapping.class).value())
            .containsExactly("/api/v1/inbound");
        assertThat(getPath("list")).isEmpty();
        assertThat(getPath("get")).containsExactly("/{recordId}");
        assertThat(Arrays.stream(InboundController.class.getDeclaredMethods())
            .filter(method -> method.isAnnotationPresent(GetMapping.class))).hasSize(2);
        assertThat(Arrays.stream(InboundController.class.getDeclaredMethods())
            .noneMatch(method -> method.isAnnotationPresent(PostMapping.class)
                || method.isAnnotationPresent(PutMapping.class))).isTrue();
    }

    @Test void listQueryMatchesInboundListParams() {
        assertThat(Arrays.stream(InboundQuery.class.getRecordComponents())
            .map(RecordComponent::getName).toList()).isEqualTo(List.of(
                "page", "perPage", "q", "containerNumber", "customerId", "warehouseId",
                "fcCode", "locationId", "status", "unloadDateFrom", "unloadDateTo",
                "receivedDateFrom", "receivedDateTo", "sortBy", "sortOrder"));
    }

    @Test void responseUsesSnakeCaseStringQuantitiesAndNullableReferences() throws Exception {
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules()
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        InboundResponse value = new InboundResponse(1, "IB2609010001", "MSCU1", null, null, null,
            LocalDate.of(2026, 9, 1), null, "LAX9", null, "1.00", "2.00", null, "3.2500",
            0, "Pending", 0, null, null, OffsetDateTime.parse("2026-09-01T10:00:00Z"),
            OffsetDateTime.parse("2026-09-01T10:00:00Z"), false, null);
        JsonNode json = mapper.readTree(mapper.writeValueAsString(value));

        assertThat(json.get("pallet_qty").isTextual()).isTrue();
        assertThat(json.get("carton_qty").isTextual()).isTrue();
        assertThat(json.get("cbm").asText()).isEqualTo("3.2500");
        assertThat(json.get("aging_days").isNumber()).isTrue();
        assertThat(json.get("status_name").asText()).isEqualTo("Pending");
        assertThat(json.get("inventory_created").asBoolean()).isFalse();
        assertThat(json.get("warehouse").isNull()).isTrue();
        assertThat(json.get("created_by").isNull()).isTrue();
    }

    private String[] getPath(String methodName) {
        Method method = Arrays.stream(InboundController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals(methodName)).findFirst().orElseThrow();
        return method.getAnnotation(GetMapping.class).value();
    }
}

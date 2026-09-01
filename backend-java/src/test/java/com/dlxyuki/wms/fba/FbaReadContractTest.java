package com.dlxyuki.wms.fba;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class FbaReadContractTest {
    @Test void exposesTheThreeSingularFastApiBaseReadRoutesWithoutWrites() throws Exception {
        RequestMapping root = FbaController.class.getAnnotation(RequestMapping.class);
        assertThat(root.value()).containsExactly("/api/v1/fba");

        assertThat(getPath("list")).isEmpty();
        assertThat(getPath("get")).containsExactly("/{fba_id}");
        assertThat(FbaAllocationController.class.getDeclaredMethod("allocations", long.class,
            com.dlxyuki.wms.user.UserAccount.class).getAnnotation(GetMapping.class).value())
            .containsExactly("/{fba_id}/allocations");
        assertThat(FbaAllocationController.class.getAnnotation(RequestMapping.class).value())
            .containsExactly("/api/v1/fba");
        assertThat(Arrays.stream(new Class<?>[]{FbaController.class, FbaAllocationController.class})
            .flatMap(type -> Arrays.stream(type.getDeclaredMethods()))
            .noneMatch(method -> method.isAnnotationPresent(PostMapping.class)
                || method.isAnnotationPresent(PutMapping.class)
                || method.isAnnotationPresent(PatchMapping.class)
                || method.isAnnotationPresent(DeleteMapping.class))).isTrue();
    }

    @Test void listQueryMatchesFastApiFbaList() {
        assertThat(Arrays.stream(FbaQuery.class.getRecordComponents())
            .map(RecordComponent::getName).toList()).isEqualTo(List.of(
                "page", "perPage", "q", "fbaNo", "customerId", "warehouseId",
                "amazonFcCode", "carrierId", "status", "containerNumber", "locationId",
                "priorityLevel", "agingMin", "agingMax", "appointmentFrom", "appointmentTo",
                "sortBy", "sortOrder"));
    }

    @Test void responseKeepsQuantityStringsNumericAgingAndNullableReferences() throws Exception {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("total_pallet_qty", "12.50");
        value.put("total_carton_qty", "24.00");
        value.put("total_weight_lbs", "1800.00");
        value.put("total_cbm", "3.2500");
        value.put("inventory_lot_count", 2);
        value.put("min_aging_days", 4);
        value.put("max_aging_days", 9);
        value.put("containers", List.of("MSCU1234567"));
        value.put("customer", null);
        value.put("carrier", null);
        JsonNode json = new ObjectMapper().readTree(new ObjectMapper().writeValueAsString(
            value));
        assertThat(json.get("total_pallet_qty").isTextual()).isTrue();
        assertThat(json.get("total_carton_qty").isTextual()).isTrue();
        assertThat(json.get("total_weight_lbs").isTextual()).isTrue();
        assertThat(json.get("total_cbm").asText()).isEqualTo("3.2500");
        assertThat(json.get("inventory_lot_count").isNumber()).isTrue();
        assertThat(json.get("min_aging_days").isNumber()).isTrue();
        assertThat(json.get("max_aging_days").isNumber()).isTrue();
        assertThat(json.get("containers").isArray()).isTrue();
        assertThat(json.get("customer").isNull()).isTrue();
        assertThat(json.get("carrier").isNull()).isTrue();
    }

    private String[] getPath(String methodName) {
        Method method = Arrays.stream(FbaController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals(methodName))
            .findFirst().orElseThrow();
        return method.getAnnotation(GetMapping.class).value();
    }
}

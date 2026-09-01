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

class FbaWorkbenchReadContractTest {
    private final ObjectMapper json = new ObjectMapper();

    @Test void exposesExactlyTheTwoWorkbenchGetsWithoutBatchOrWrites() {
        assertThat(getPath("workbench")).containsExactly("/workbench");
        assertThat(getPath("workbenchDetail")).containsExactly("/{fba_id}/workbench-detail");
        assertThat(Arrays.stream(FbaController.class.getDeclaredMethods())
            .filter(method -> method.isAnnotationPresent(GetMapping.class))).hasSize(4);
        assertThat(Arrays.stream(FbaController.class.getDeclaredMethods())
            .noneMatch(method -> method.isAnnotationPresent(PostMapping.class)
                || method.isAnnotationPresent(PutMapping.class)
                || method.isAnnotationPresent(PatchMapping.class)
                || method.isAnnotationPresent(DeleteMapping.class))).isTrue();
    }

    @Test void workbenchQueryMatchesFastApiListWorkbench() {
        assertThat(Arrays.stream(WorkbenchQuery.class.getRecordComponents())
            .map(RecordComponent::getName).toList()).isEqualTo(List.of(
                "page", "perPage", "warehouseId", "customerId", "q", "stage", "priority",
                "onlyOld", "unloadFrom", "unloadTo", "agingMin", "agingMax", "amazonFcCode",
                "containerNumber", "locationId", "carrierId", "fbaStatus", "outboundStatus",
                "pickingStatus", "bolStatus", "stNumber", "poNumber", "scheduledFrom",
                "scheduledTo", "appointmentFrom", "appointmentTo", "sortBy", "sortOrder"));
    }

    @Test void listAndDetailKeepSnakeCaseShapeAndNumericContract() throws Exception {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("total_pallet_qty", "12.50");
        row.put("total_carton_qty", "24.00");
        row.put("total_weight_lbs", "1800.00");
        row.put("total_cbm", "3.2500");
        row.put("warehouse_days", 8);
        row.put("outbound_days_remaining", null);
        row.put("priority_rank", 2);
        row.put("dispatch_priority", "NORMAL");
        row.put("dispatch_priority_rank", 3);
        row.put("max_aging_days", 8);
        row.put("containers_preview", List.of("MSCU1234567"));
        row.put("locations_preview", List.of("A-01"));

        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("task_count", 1);
        summary.put("total_pallet_qty", "12.50");
        summary.put("total_carton_qty", "24.00");
        summary.put("total_weight_lbs", "1800.00");
        summary.put("total_cbm", "3.2500");
        summary.put("average_aging_days", 8);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("data", List.of(row));
        response.put("meta", Map.of("page", 1, "per_page", 20, "total", 1, "total_pages", 1));
        response.put("summary", summary);
        response.put("stage_counts", Map.of("all", 1));
        response.put("permissions", Map.of("can_export", true, "can_operate", false));
        JsonNode list = json.valueToTree(response);

        assertThat(list.fieldNames()).toIterable().containsExactly(
            "data", "meta", "summary", "stage_counts", "permissions");
        for (String field : List.of("total_pallet_qty", "total_carton_qty",
            "total_weight_lbs", "total_cbm")) {
            assertThat(list.at("/data/0/" + field).isTextual()).isTrue();
            assertThat(list.at("/summary/" + field).isTextual()).isTrue();
        }
        assertThat(list.at("/data/0/dispatch_priority").asText()).isEqualTo("NORMAL");
        assertThat(list.at("/data/0/dispatch_priority_rank").asInt()).isEqualTo(3);
        assertThat(list.at("/data/0/containers_preview").isArray()).isTrue();
        assertThat(list.at("/data/0/locations_preview").isArray()).isTrue();

        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("basic", Map.of());
        detail.put("inventory_sources", List.of());
        detail.put("picking", List.of());
        detail.put("bol", null);
        detail.put("outbound", null);
        detail.put("audit", List.of());
        detail.put("workflow", List.of());
        detail.put("permissions", Map.of("can_export", true, "can_operate", false));
        JsonNode detailJson = json.readTree(json.writeValueAsString(detail));
        assertThat(detailJson.fieldNames()).toIterable().containsExactly(
            "basic", "inventory_sources", "picking", "bol", "outbound", "audit",
            "workflow", "permissions");
        assertThat(detailJson.get("bol").isNull()).isTrue();
        assertThat(detailJson.get("outbound").isNull()).isTrue();
    }

    private String[] getPath(String methodName) {
        Method method = Arrays.stream(FbaController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals(methodName))
            .findFirst().orElseThrow();
        return method.getAnnotation(GetMapping.class).value();
    }
}

package com.dlxyuki.wms.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.user.UserAccount;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

class OutboundWorkbenchReadContractTest {
    @Test
    void exposesOnlyTheAcceptedWorkbenchGetPaths() {
        assertThat(getPath("workbench")).containsExactly("/workbench");
        assertThat(getPath("workbenchDetail")).containsExactly("/{id}/workbench-detail");
    }

    @Test
    void listParametersAndDefaultsMatchFastApi() {
        Method method = method("workbench");
        List<String> parameters = Arrays.stream(method.getParameters())
            .filter(parameter -> parameter.isAnnotationPresent(RequestParam.class))
            .map(parameter -> {
                RequestParam request = parameter.getAnnotation(RequestParam.class);
                return request.name().isEmpty() ? parameter.getName() : request.name();
            }).toList();

        assertThat(parameters).containsExactly(
            "page", "per_page", "q", "status", "ob_type", "warehouse_id",
            "carrier_id", "sort_by", "sort_order");
        assertThat(defaultValue(method, "page")).isEqualTo("1");
        assertThat(defaultValue(method, "per_page")).isEqualTo("20");
        assertThat(defaultValue(method, "sort_by")).isEqualTo("created_at");
        assertThat(defaultValue(method, "sort_order")).isEqualTo("desc");
    }

    @Test
    void listHasFourSectionsAndKeepsQuantitiesAsStrings() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("data", List.of(Map.of("allocated_pallet_qty", "12.50")));
        response.put("meta", Map.of("page", 1, "per_page", 20, "total", 1, "total_pages", 1));
        response.put("summary", Map.of("allocated_pallet_qty", "12.50"));
        response.put("status_counts", Map.of("all", 1));

        ObjectMapper mapper = new ObjectMapper();
        JsonNode json = mapper.readTree(mapper.writeValueAsString(response));
        assertThat(response.keySet()).containsExactly("data", "meta", "summary", "status_counts");
        assertThat(json.at("/data/0/allocated_pallet_qty").isTextual()).isTrue();
        assertThat(json.at("/summary/allocated_pallet_qty").isTextual()).isTrue();
    }

    @Test
    void detailHasExactlyTheNineFastApiSections() {
        OutboundService service = mock(OutboundService.class);
        OutboundController controller = new OutboundController(service);
        UserAccount user = mock(UserAccount.class);
        Map<String, Object> response = new LinkedHashMap<>();
        for (String key : List.of("basic", "allocations", "picking", "bols",
                "remaining_sources", "summary", "workflow", "audit", "allowed_actions")) {
            response.put(key, List.of());
        }
        when(service.workbenchDetail(17L, user)).thenReturn(response);

        @SuppressWarnings("unchecked")
        Map<String, Object> actual = (Map<String, Object>) controller.workbenchDetail(17L, user);
        assertThat(actual.keySet()).containsExactly(
            "basic", "allocations", "picking", "bols", "remaining_sources",
            "summary", "workflow", "audit", "allowed_actions");
    }

    private Method method(String name) {
        return Arrays.stream(OutboundController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals(name))
            .findFirst().orElseThrow();
    }

    private String[] getPath(String name) {
        return method(name).getAnnotation(GetMapping.class).value();
    }

    private String defaultValue(Method method, String name) {
        return Arrays.stream(method.getParameters())
            .filter(parameter -> parameter.isAnnotationPresent(RequestParam.class))
            .filter(parameter -> {
                RequestParam request = parameter.getAnnotation(RequestParam.class);
                String parameterName = request.name().isEmpty() ? parameter.getName() : request.name();
                return parameterName.equals(name);
            })
            .findFirst().orElseThrow().getAnnotation(RequestParam.class).defaultValue();
    }
}

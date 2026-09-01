package com.dlxyuki.wms.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.user.UserAccount;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

class OutboundReadContractTest {
    @Test void exposesPluralFastApiListAndDetailRoutes() {
        RequestMapping root = OutboundController.class.getAnnotation(RequestMapping.class);
        assertThat(root.value()).containsExactly("/api/v1/outbounds");

        assertThat(getPath("list")).isEmpty();
        assertThat(getPath("get")).containsExactly("/{ob_id}");
        assertThat(getPath("allocations")).containsExactly("/{ob_id}/allocations");
    }

    @Test void retainsWorkbenchRoutesAndOnlyRegistersTheApprovedAdditionalReadRoute() {
        assertThat(getPath("workbench")).containsExactly("/workbench");
        assertThat(getPath("workbenchDetail")).containsExactly("/{id}/workbench-detail");
        assertThat(getPath("readiness")).containsExactly("/{ob_id}/dispatch-readiness");
        assertThat(Arrays.stream(OutboundController.class.getDeclaredMethods())
            .filter(method -> method.isAnnotationPresent(GetMapping.class))).hasSize(6);
    }

    @Test void listQueryMatchesFastApiFiltersAndPaginationContract() {
        assertThat(Arrays.stream(OutboundQuery.class.getRecordComponents())
            .map(RecordComponent::getName).toList()).isEqualTo(List.of(
                "page", "perPage", "q", "obNo", "status", "obType", "customerId",
                "warehouseId", "carrierId", "fbaShipmentId", "fcCode", "delCode",
                "agentCode", "sortBy", "sortOrder"));

        Method list = method("list");
        assertThat(Arrays.stream(list.getParameters())
            .filter(parameter -> parameter.isAnnotationPresent(RequestParam.class))
            .map(this::requestName).toList()).containsExactly(
                "page", "per_page", "q", "ob_no", "status", "ob_type",
                "customer_id", "warehouse_id", "carrier_id", "fba_shipment_id",
                "fc_code", "del_code", "agent_code", "sort_by", "sort_order");
        assertThat(defaultValue(list, "page")).isEqualTo("1");
        assertThat(defaultValue(list, "per_page")).isEqualTo("20");
        assertThat(defaultValue(list, "sort_by")).isEqualTo("id");
        assertThat(defaultValue(list, "sort_order")).isEqualTo("desc");
    }

    @Test void listKeepsDataAndMetaWhenNoRowsMatch() {
        OutboundService service = mock(OutboundService.class);
        OutboundController controller = new OutboundController(service);
        UserAccount user = mock(UserAccount.class);
        OutboundQuery query = new OutboundQuery(1,20,"missing",null,null,null,null,null,null,null,null,null,null,"id","desc");
        Map<String,Object> response = new LinkedHashMap<>();
        response.put("data", List.of());
        response.put("meta", Map.of("page",1,"per_page",20,"total",0,"total_pages",0));
        when(service.list(query,user)).thenReturn(response);

        assertThat(controller.list(1,20,"missing",null,null,null,null,null,null,null,null,null,null,"id","desc",user))
            .isEqualTo(response);
        assertThat(response.keySet()).containsExactly("data","meta");
    }

    @Test void detailAndAllocationQuantityValuesRemainJsonStrings() throws Exception {
        OutboundService service = mock(OutboundService.class);
        OutboundController controller = new OutboundController(service);
        UserAccount user = mock(UserAccount.class);
        Map<String,Object> detail = Map.of("id",17L,"total_pallet_qty","12.50","remaining_carton_qty","3.00");
        List<Map<String,Object>> allocations = List.of(Map.of(
            "id",1L,"allocated_pallet_qty","12.50","completed_cbm","3.2500"));
        when(service.get(17L,user)).thenReturn(detail);
        when(service.allocations(17L,user)).thenReturn(allocations);

        ObjectMapper mapper = new ObjectMapper();
        JsonNode detailJson = mapper.readTree(mapper.writeValueAsString(controller.get(17L,user)));
        JsonNode allocationsJson = mapper.readTree(mapper.writeValueAsString(controller.allocations(17L,user)));
        assertThat(detailJson.get("total_pallet_qty").isTextual()).isTrue();
        assertThat(detailJson.get("remaining_carton_qty").asText()).isEqualTo("3.00");
        assertThat(allocationsJson.at("/0/allocated_pallet_qty").isTextual()).isTrue();
        assertThat(allocationsJson.at("/0/completed_cbm").asText()).isEqualTo("3.2500");
    }

    private Method method(String methodName) {
        return Arrays.stream(OutboundController.class.getDeclaredMethods())
            .filter(candidate -> candidate.getName().equals(methodName))
            .findFirst().orElseThrow();
    }

    private String[] getPath(String methodName) {
        return method(methodName).getAnnotation(GetMapping.class).value();
    }

    private String requestName(Parameter parameter) {
        RequestParam request = parameter.getAnnotation(RequestParam.class);
        return request.name().isEmpty() ? parameter.getName() : request.name();
    }

    private String defaultValue(Method method,String name) {
        return Arrays.stream(method.getParameters())
            .filter(parameter -> parameter.isAnnotationPresent(RequestParam.class))
            .filter(parameter -> requestName(parameter).equals(name))
            .findFirst().orElseThrow().getAnnotation(RequestParam.class).defaultValue();
    }
}

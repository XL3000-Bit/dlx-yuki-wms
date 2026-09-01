package com.dlxyuki.wms.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;

class OutboundDispatchReadinessContractTest {
    @Test void exposesOnlyTheApprovedGetRouteAndDelegatesThroughScopedService() throws Exception {
        GetMapping mapping = OutboundController.class.getDeclaredMethod(
            "readiness", long.class, UserAccount.class).getAnnotation(GetMapping.class);
        assertThat(mapping.value()).containsExactly("/{ob_id}/dispatch-readiness");

        OutboundRepository repository = mock(OutboundRepository.class);
        UserAccount user = mock(UserAccount.class);
        Map<String,Object> visible = Map.of("id", 41L);
        Map<String,Object> response = Map.of("status", "READY");
        when(repository.find(41L,user)).thenReturn(Optional.of(visible));
        when(repository.readiness(41L)).thenReturn(response);
        OutboundController controller = new OutboundController(new OutboundService(repository));
        assertThat(controller.readiness(41L,user)).isSameAs(response);
    }

    @Test void invisibleOrMissingOutboundIsNotFoundBeforeReadinessIsCalculated() {
        OutboundRepository repository = mock(OutboundRepository.class);
        UserAccount user = mock(UserAccount.class);
        when(repository.find(404L,user)).thenReturn(Optional.empty());
        OutboundService service = new OutboundService(repository);
        assertThatThrownBy(() -> service.readiness(404L,user))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("Outbound order not found");
    }

    @Test void loadMemberUsesTheSingleFastApiBlockingCheckAndDedicatedErrorCode() {
        NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
        Map<String,Object> outbound = new LinkedHashMap<>();
        outbound.put("status", 3);
        outbound.put("carrier_id", 7L);
        outbound.put("load_id", 9L);
        when(jdbc.queryForMap(anyString(),anyMap())).thenReturn(outbound);

        Map<String,Object> result = new OutboundRepository(jdbc).readiness(41L);
        assertThat(result.keySet()).containsExactly(
            "status", "checks", "blocking_reasons", "blocking_codes", "error_code");
        assertThat(result.get("status")).isEqualTo("NOT_READY");
        assertThat(result.get("blocking_reasons")).isEqualTo(List.of("Must dispatch through Load"));
        assertThat(result.get("blocking_codes")).isEqualTo(List.of("LOAD_DISPATCH_REQUIRED"));
        assertThat(result.get("error_code")).isEqualTo("DISPATCH_THROUGH_LOAD_REQUIRED");
        assertThat(checks(result)).hasSize(1);
        assertThat(checks(result).get(0)).containsEntry("key", "load_dispatch")
            .containsEntry("label", "Standalone dispatch")
            .containsEntry("passed", false)
            .containsEntry("reason", "Must dispatch through Load")
            .containsEntry("code", "LOAD_DISPATCH_REQUIRED")
            .containsEntry("route", null);
    }

    @Test void standaloneChecksKeepFastApiOrderRoutesAndNullsForPassingItems() {
        NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
        Map<String,Object> outbound = new LinkedHashMap<>();
        outbound.put("status", 3);
        outbound.put("carrier_id", 7L);
        outbound.put("load_id", null);
        Map<String,Object> metrics = Map.of(
            "allocations", 1L, "allocated", new BigDecimal("4"),
            "picked", new BigDecimal("4"), "bols", 1L, "exceptions", 0L);
        when(jdbc.queryForMap(anyString(),anyMap())).thenReturn(outbound,metrics);

        Map<String,Object> result = new OutboundRepository(jdbc).readiness(42L);
        assertThat(result.get("status")).isEqualTo("READY");
        assertThat(result.get("blocking_reasons")).isEqualTo(List.of());
        assertThat(result.get("blocking_codes")).isEqualTo(List.of());
        assertThat(result.get("error_code")).isNull();
        assertThat(checks(result)).extracting(check -> check.get("key")).containsExactly(
            "status", "allocation", "picking", "bol", "carrier", "exceptions");
        assertThat(checks(result)).extracting(check -> check.get("route")).containsExactly(
            null, "/outbound/picking", "/outbound/picking", "/outbound/bol", null, "/trouble-shoot");
        assertThat(checks(result)).allSatisfy(check -> {
            assertThat(check.get("passed")).isEqualTo(true);
            assertThat(check.get("reason")).isNull();
            assertThat(check.get("code")).isNull();
        });
    }

    @Test void ordinaryFailuresAggregateReasonsAndCodesInCheckOrderWithoutErrorCode() {
        NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
        Map<String,Object> outbound = new LinkedHashMap<>();
        outbound.put("status", 0);
        outbound.put("carrier_id", null);
        outbound.put("load_id", null);
        Map<String,Object> metrics = Map.of(
            "allocations", 0L, "allocated", BigDecimal.ZERO,
            "picked", BigDecimal.ZERO, "bols", 0L, "exceptions", 1L);
        when(jdbc.queryForMap(anyString(),anyMap())).thenReturn(outbound,metrics);

        Map<String,Object> result = new OutboundRepository(jdbc).readiness(43L);
        assertThat(result.get("status")).isEqualTo("NOT_READY");
        assertThat(result.get("blocking_codes")).isEqualTo(List.of(
            "OUTBOUND_NOT_CONFIRMED", "ALLOCATION_REQUIRED", "PICKING_INCOMPLETE",
            "SYSTEM_BOL_REQUIRED", "CARRIER_REQUIRED", "ACTIVE_EXCEPTION"));
        assertThat(result.get("error_code")).isNull();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String,Object>> checks(Map<String,Object> result) {
        return (List<Map<String,Object>>) result.get("checks");
    }
}

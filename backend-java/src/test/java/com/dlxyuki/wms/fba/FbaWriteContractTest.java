package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.core.MethodParameter;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@ExtendWith(MockitoExtension.class)
class FbaWriteContractTest {
    @Mock FbaRepository repository;

    private FbaService service;

    @BeforeEach
    void setUp() {
        service = new FbaService(repository);
    }

    @Test
    void postAndPutExposeOnlyTheApprovedWriteContract() throws Exception {
        FbaService controllerService = mock(FbaService.class);
        Map<String, Object> response = Map.of(
            "id", 41L, "fba_no", "FBA2609010001", "status", 0,
            "amazon_fc_code", "ONT8", "total_pallet_qty", "0.0000"
        );
        UserAccount principal = mock(UserAccount.class);
        when(controllerService.create(any(), same(principal))).thenReturn(response);
        when(controllerService.update(eq(41L), any(), same(principal))).thenReturn(response);
        HandlerMethodArgumentResolver authenticationPrincipal = new HandlerMethodArgumentResolver() {
            @Override
            public boolean supportsParameter(MethodParameter parameter) {
                return parameter.hasParameterAnnotation(AuthenticationPrincipal.class);
            }

            @Override
            public Object resolveArgument(MethodParameter parameter, ModelAndViewContainer mavContainer,
                                          NativeWebRequest webRequest, WebDataBinderFactory binderFactory) {
                return principal;
            }
        };
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new FbaController(controllerService))
            .setCustomArgumentResolvers(authenticationPrincipal)
            .build();
        String body = """
            {"warehouseId":2,"customerId":3,"amazonFcCode":" ont8 ","remark":"JAVA-WRITE-TEST contract"}
            """;

        mvc.perform(post("/api/v1/fba").contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.fba_no").value("FBA2609010001"))
            .andExpect(jsonPath("$.total_pallet_qty").value("0.0000"));
        mvc.perform(put("/api/v1/fba/41").contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(41));
    }

    @Test
    void createNormalizesFcChecksReferencesAndWritesAuditWithoutDatabase() {
        UserAccount user = writableUser();
        when(repository.warehouseExists(2L)).thenReturn(true);
        when(repository.customerExists(3L)).thenReturn(true);
        when(repository.carrierExists(4L)).thenReturn(true);
        when(repository.amazonFcAddressId("ONT8")).thenReturn(9L);
        when(repository.create(any(), eq(7L), any())).thenReturn(41L);
        when(repository.snapshot(41L)).thenReturn("{\"id\":41}");
        when(repository.find(41L, user)).thenReturn(Optional.of(Map.of(
            "id", 41L, "fba_no", "FBA2609010001", "status", 0,
            "amazon_fc_code", "ONT8", "total_pallet_qty", "0.0000"
        )));

        Object result = service.create(new FbaWriteRequest(3L, 2L, " ont8 ", 4L,
            "2026-09-01T10:00:00-07:00", null, " JAVA-WRITE-TEST ref ", null, null,
            " JAVA-WRITE-TEST note "), user);

        ArgumentCaptor<FbaService.WriteValues> values = ArgumentCaptor.forClass(FbaService.WriteValues.class);
        verify(repository).create(values.capture(), eq(7L), any());
        assertEquals("ONT8", values.getValue().amazonFcCode());
        assertEquals(9L, values.getValue().amazonFcAddressId());
        assertEquals("JAVA-WRITE-TEST ref", values.getValue().referenceNo());
        assertEquals("JAVA-WRITE-TEST note", values.getValue().remark());
        verify(repository).audit("CREATE_FBA", 41L, 7L, null, "{\"id\":41}");
        assertEquals("ONT8", ((Map<?, ?>) result).get("amazon_fc_code"));
    }

    @Test
    void updateRequiresVisibleShipmentAndAuditsBeforeAndAfter() {
        UserAccount user = writableUser();
        when(repository.find(41L, user))
            .thenReturn(Optional.of(Map.of("id", 41L)))
            .thenReturn(Optional.of(Map.of("id", 41L, "fba_no", "FBA2609010001")));
        when(repository.warehouseExists(2L)).thenReturn(true);
        when(repository.amazonFcAddressId("LGB8")).thenReturn(null);
        when(repository.snapshot(41L)).thenReturn("{\"remark\":\"old\"}", "{\"remark\":\"new\"}");

        service.update(41L, new FbaWriteRequest(null, 2L, "lgb8", null,
            null, null, null, null, null, "new"), user);

        verify(repository).update(eq(41L), any());
        verify(repository).audit("UPDATE_FBA", 41L, 7L,
            "{\"remark\":\"old\"}", "{\"remark\":\"new\"}");
    }

    @Test
    void readOnlyAccountIsRejectedBeforeAnyWrite() {
        UserAccount readOnly = mock(UserAccount.class);
        when(readOnly.role()).thenReturn("VIEWER");

        assertThrows(ApiException.class, () -> service.create(
            new FbaWriteRequest(null, 2L, "ONT8", null, null, null, null, null, null, null), readOnly));
        verifyNoInteractions(repository);
    }

    private UserAccount writableUser() {
        UserAccount user = mock(UserAccount.class);
        when(user.id()).thenReturn(7L);
        when(user.role()).thenReturn("ADMIN");
        return user;
    }
}

package com.dlxyuki.wms.inventory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import com.dlxyuki.wms.user.UserAccount;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.lang.reflect.Method;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class InventoryReadContractTest {
    @Test void exposesOnlyTheThreeApprovedReadRoutes() {
        assertThat(InventoryController.class.getAnnotation(RequestMapping.class).value())
            .containsExactly("/api/v1/inventory");
        assertThat(path("list")).isEmpty();
        assertThat(path("get")).containsExactly("/{lotId}");
        assertThat(path("transactions")).containsExactly("/{lotId}/transactions");
        assertThat(Arrays.stream(InventoryController.class.getDeclaredMethods())
            .filter(x -> x.isAnnotationPresent(GetMapping.class))).hasSize(3);
    }

    @Test void transactionsRequireScopedLotAndKeepQuantitiesAsStrings() throws Exception {
        InventoryRepository repository = mock(InventoryRepository.class);
        InventoryService service = spy(new InventoryService(repository));
        UserAccount user = mock(UserAccount.class);
        InventoryResponse lot = mock(InventoryResponse.class);
        when(repository.find(8L,user)).thenReturn(Optional.of(lot));
        InventoryTransactionResponse row = new InventoryTransactionResponse(4L,"MOVE","1.00","2.00","3.00","4.0000",
            null,null,null,null,null,null,null,new InventoryTransactionResponse.CreatedBy(1L,"Admin"),null);
        when(repository.transactions(8L)).thenReturn(List.of(row));

        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules()
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        JsonNode json = mapper.readTree(mapper.writeValueAsString(service.transactions(8L,user)));
        assertThat(json.at("/0/pallet_delta").isTextual()).isTrue();
        assertThat(json.at("/0/cbm_delta").asText()).isEqualTo("4.0000");
        verify(repository).find(8L,user);
        verify(repository).transactions(8L);
    }

    private String[] path(String name) { return method(name).getAnnotation(GetMapping.class).value(); }
    private Method method(String name) { return Arrays.stream(InventoryController.class.getDeclaredMethods())
        .filter(x -> x.getName().equals(name)).findFirst().orElseThrow(); }
}

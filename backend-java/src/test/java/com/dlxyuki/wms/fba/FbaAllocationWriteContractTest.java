package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;

import java.math.BigDecimal;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class FbaAllocationWriteContractTest {
    @Mock FbaRepository repository;
    private FbaService service;

    @BeforeEach
    void setUp() { service = new FbaService(repository); }

    @Test
    void allocateConsumesInventoryAccumulatesAllocationAndAudits() {
        UserAccount user = writableUser();
        var shipment = shipment(0);
        var lot = lot(q("10", "20", "30", "40"), q("1", "2", "3", "4"), "ONT8");
        when(repository.lockShipment(41L, user)).thenReturn(Optional.of(shipment));
        when(repository.lockLot(51L, user)).thenReturn(Optional.of(lot));
        when(repository.lockAllocationByLot(41L, 51L)).thenReturn(Optional.of(
            new FbaRepository.AllocationLock(61L, 41L, 51L, q("1", "1", "1", "1"))));
        when(repository.lotSnapshot(51L)).thenReturn("before", "after");
        when(repository.allocationRead(41L, 61L, "ONT8")).thenReturn(Optional.of(Map.of(
            "id", 61L, "allocated_pallet_qty", "3.0000", "allocated_carton_qty", "4.0000")));

        Object result = service.allocate(41L,
            new FbaAllocateRequest(51L, bd("2"), bd("3"), bd("4"), bd("5"), false), user);

        verify(repository).updateLot(51L, q("8", "17", "26", "35"), q("3", "5", "7", "9"), lot);
        verify(repository).updateAllocation(61L, q("3", "4", "5", "6"));
        verify(repository).updateFbaStatus(41L, 2);
        verify(repository).inventoryTransaction(51L, "FBA_ALLOCATE", q("-2", "-3", "-4", "-5"),
            41L, "Allocated to FBA2609020001", 7L, "before", "after");
        verify(repository).audit("ALLOCATE_FBA_INVENTORY", 41L, 7L, "before", "after");
        assertEquals("3.0000", ((Map<?, ?>) result).get("allocated_pallet_qty"));
    }

    @Test
    void releaseTreatsNullAsAllAndDoesNotChangeFbaStatus() {
        UserAccount user = writableUser();
        var lot = lot(q("8", "17", "26", "35"), q("3", "5", "7", "9"), "ONT8");
        when(repository.lockShipment(41L, user)).thenReturn(Optional.of(shipment(2)));
        when(repository.lockAllocation(41L, 61L)).thenReturn(Optional.of(
            new FbaRepository.AllocationLock(61L, 41L, 51L, q("3", "4", "5", "6"))));
        when(repository.lockLot(51L, user)).thenReturn(Optional.of(lot));
        when(repository.lotSnapshot(51L)).thenReturn("before", "after");
        when(repository.allocationRead(41L, 61L, "ONT8")).thenReturn(Optional.of(Map.of(
            "id", 61L, "allocated_pallet_qty", "0.0000")));

        service.release(41L, 61L, new FbaReleaseRequest(null, bd("2"), null, bd("1"), " test release "), user);

        verify(repository).updateAllocation(61L, q("0", "2", "0", "5"));
        verify(repository).updateLot(51L, q("11", "19", "31", "36"), q("0", "3", "2", "8"), lot);
        verify(repository).inventoryTransaction(51L, "FBA_RELEASE", q("3", "2", "5", "1"),
            41L, "test release", 7L, "before", "after");
        verify(repository).audit("RELEASE_FBA_INVENTORY", 41L, 7L, "before", "after");
        verify(repository, never()).updateFbaStatus(anyLong(), anyInt());
    }

    @Test
    void authorizationVisibilityAndValidationStatusesMatchContract() {
        FbaAllocateRequest valid = new FbaAllocateRequest(51L, bd("1"), null, null, null, false);
        assertStatus(HttpStatus.UNAUTHORIZED, () -> service.allocate(41L, valid, null));
        UserAccount viewer = mock(UserAccount.class); when(viewer.role()).thenReturn("VIEWER");
        assertStatus(HttpStatus.FORBIDDEN, () -> service.allocate(41L, valid, viewer));

        UserAccount user = writableUser();
        when(repository.lockShipment(41L, user)).thenReturn(Optional.empty());
        assertStatus(HttpStatus.NOT_FOUND, () -> service.allocate(41L, valid, user));

        reset(repository);
        when(repository.lockShipment(41L, user)).thenReturn(Optional.of(shipment(7)));
        assertStatus(HttpStatus.CONFLICT, () -> service.allocate(41L, valid, user));

        reset(repository);
        when(repository.lockShipment(41L, user)).thenReturn(Optional.of(shipment(0)));
        when(repository.lockLot(51L, user)).thenReturn(Optional.of(lot(q("1", "1", "1", "1"), q("0", "0", "0", "0"), "ONT8")));
        assertStatus(HttpStatus.UNPROCESSABLE_ENTITY, () -> service.allocate(41L,
            new FbaAllocateRequest(51L, bd("0"), bd("0"), bd("0"), bd("0"), false), user));
        assertStatus(HttpStatus.CONFLICT, () -> service.allocate(41L,
            new FbaAllocateRequest(51L, bd("2"), null, null, null, false), user));

        reset(repository);
        when(repository.lockShipment(41L, user)).thenReturn(Optional.of(shipment(2)));
        when(repository.lockAllocation(41L, 999L)).thenReturn(Optional.empty());
        assertStatus(HttpStatus.NOT_FOUND, () -> service.release(41L, 999L,
            new FbaReleaseRequest(null, null, null, null, null), user));
    }

    @Test
    void unconfirmedFcMismatchCarriesDedicatedConflictSignal() {
        UserAccount user = writableUser();
        when(repository.lockShipment(41L, user)).thenReturn(Optional.of(shipment(0)));
        when(repository.lockLot(51L, user)).thenReturn(Optional.of(lot(q("2", "0", "0", "0"), q("0", "0", "0", "0"), "LGB8")));
        FbaService.FcMismatchException error = assertThrows(FbaService.FcMismatchException.class,
            () -> service.allocate(41L, new FbaAllocateRequest(51L, bd("1"), null, null, null, false), user));
        assertEquals("Inventory FC differs from FBA FC", error.getMessage());
    }

    private void assertStatus(HttpStatus status, Runnable call) {
        ApiException error = assertThrows(ApiException.class, call::run);
        assertEquals(status, error.status());
    }
    private UserAccount writableUser() {
        UserAccount user = mock(UserAccount.class);
        lenient().when(user.id()).thenReturn(7L);
        lenient().when(user.role()).thenReturn("ADMIN");
        return user;
    }
    private FbaRepository.ShipmentLock shipment(int status) {
        return new FbaRepository.ShipmentLock(41L, "FBA2609020001", 2L, 3L, "ONT8", status);
    }
    private FbaRepository.LotLock lot(FbaService.Quantities available, FbaService.Quantities allocated, String fc) {
        return new FbaRepository.LotLock(51L, 2L, 3L, fc, bd("10"), bd("20"), available, allocated, bd("0"), bd("0"));
    }
    private FbaService.Quantities q(String p, String c, String w, String v) {
        return new FbaService.Quantities(bd(p), bd(c), bd(w), bd(v));
    }
    private BigDecimal bd(String value) { return new BigDecimal(value); }
}

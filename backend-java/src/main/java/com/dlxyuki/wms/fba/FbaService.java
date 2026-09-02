package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

@Service
public class FbaService {
    private static final ZoneId BUSINESS_ZONE = ZoneId.of("America/Los_Angeles");
    private static final Set<String> WRITE_ROLES = Set.of("ADMIN", "MANAGER", "OUTBOUND", "WAREHOUSE");
    private final FbaRepository repository;
    public FbaService(FbaRepository repository) { this.repository=repository; }
    Object list(FbaQuery q, UserAccount u) { return repository.list(q,u); }
    Object workbench(WorkbenchQuery q, UserAccount u) { return repository.workbench(q,u); }
    Object workbenchDetail(long id, UserAccount u) { return repository.workbenchDetail(id,u)
        .orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"FBA shipment not found")); }
    Object get(long id, UserAccount u) { return repository.find(id,u).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"FBA shipment not found")); }
    Object allocations(long id, UserAccount u) { return repository.findAllocations(id,u)
        .orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"FBA shipment not found")); }

    @Transactional
    Object allocate(long id, FbaAllocateRequest request, UserAccount user) {
        requireWrite(user);
        var shipment = repository.lockShipment(id, user)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "FBA shipment not found"));
        if (shipment.status() == 7 || shipment.status() == 9)
            throw new ApiException(HttpStatus.CONFLICT, "FBA status does not allow allocation");
        if (request == null || request.inventoryLotId() == null)
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "inventory_lot_id is required");
        var lot = repository.lockLot(request.inventoryLotId(), user)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Inventory lot not found"));
        if (lot.warehouseId() != shipment.warehouseId())
            throw new ApiException(HttpStatus.CONFLICT, "Inventory and FBA warehouses differ");
        boolean mismatch = hasText(lot.fcCode()) && !lot.fcCode().equalsIgnoreCase(shipment.amazonFcCode());
        if (mismatch && !Boolean.TRUE.equals(request.confirmFcMismatch()))
            throw new FcMismatchException("Inventory FC differs from FBA FC");
        Quantities amount = quantities(request.palletQty(), request.cartonQty(), request.weightLbs(), request.cbm());
        requirePositive(amount, "At least one allocation quantity is required");
        if (amount.exceeds(lot.available()))
            throw new ApiException(HttpStatus.CONFLICT, "Allocation exceeds currently available inventory");

        String before = repository.lotSnapshot(lot.id());
        repository.updateLot(lot.id(), lot.available().minus(amount), lot.allocated().plus(amount), lot);
        var existing = repository.lockAllocationByLot(id, lot.id());
        long allocationId = existing.map(a -> {
            repository.updateAllocation(a.id(), a.quantities().plus(amount)); return a.id();
        }).orElseGet(() -> repository.insertAllocation(id, lot.id(), amount, user.id()));
        if (shipment.status() == 0 || shipment.status() == 1) repository.updateFbaStatus(id, 2);
        String after = repository.lotSnapshot(lot.id());
        repository.inventoryTransaction(lot.id(), "FBA_ALLOCATE", amount.negate(), id,
            "Allocated to " + shipment.fbaNo(), user.id(), before, after);
        repository.audit("ALLOCATE_FBA_INVENTORY", id, user.id(), before, after);
        return repository.allocationRead(id, allocationId, shipment.amazonFcCode())
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Allocation not found"));
    }

    @Transactional
    Object release(long id, long allocationId, FbaReleaseRequest request, UserAccount user) {
        requireWrite(user);
        var shipment = repository.lockShipment(id, user)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "FBA shipment not found"));
        var allocation = repository.lockAllocation(id, allocationId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Allocation not found"));
        var lot = repository.lockLot(allocation.lotId(), user)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Inventory lot not found"));
        Quantities current = allocation.quantities();
        Quantities amount = new Quantities(orAll(request == null ? null : request.palletQty(), current.pallet()),
            orAll(request == null ? null : request.cartonQty(), current.carton()),
            orAll(request == null ? null : request.weightLbs(), current.weight()),
            orAll(request == null ? null : request.cbm(), current.cbm()));
        validateNonNegative(amount);
        requirePositive(amount, "No quantity to release");
        if (amount.exceeds(current)) throw new ApiException(HttpStatus.CONFLICT, "Release exceeds allocation");

        String before = repository.lotSnapshot(lot.id());
        repository.updateAllocation(allocationId, current.minus(amount));
        repository.updateLot(lot.id(), lot.available().plus(amount), lot.allocated().minus(amount), lot);
        String after = repository.lotSnapshot(lot.id());
        String remark = request == null || !hasText(request.remark()) ? "Released from " + shipment.fbaNo() : request.remark().trim();
        repository.inventoryTransaction(lot.id(), "FBA_RELEASE", amount, id, remark, user.id(), before, after);
        repository.audit("RELEASE_FBA_INVENTORY", id, user.id(), before, after);
        return repository.allocationRead(id, allocationId, shipment.amazonFcCode())
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Allocation not found"));
    }

    @Transactional
    Object create(FbaWriteRequest request, UserAccount user) {
        requireWrite(user);
        WriteValues values = validate(request, user);
        long id = repository.create(values, user.id(), LocalDate.now(BUSINESS_ZONE));
        repository.audit("CREATE_FBA", id, user.id(), null, repository.snapshot(id));
        return get(id, user);
    }

    @Transactional
    Object update(long id, FbaWriteRequest request, UserAccount user) {
        requireWrite(user);
        repository.find(id, user).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"FBA shipment not found"));
        WriteValues values = validate(request, user);
        String before = repository.snapshot(id);
        repository.update(id, values);
        repository.audit("UPDATE_FBA", id, user.id(), before, repository.snapshot(id));
        return get(id, user);
    }

    private WriteValues validate(FbaWriteRequest request, UserAccount user) {
        if (request == null || request.warehouseId() == null || request.amazonFcCode() == null
            || request.amazonFcCode().isBlank()) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "warehouse_id and amazon_fc_code are required");
        }
        if (!allowed(user.warehouseScopeMode(), user.warehouseIds(), request.warehouseId(), user.role())
            || !allowed(user.customerScopeMode(), user.customerIds(), request.customerId(), user.role())) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Insufficient scope");
        }
        if (!repository.warehouseExists(request.warehouseId()))
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Warehouse not found");
        if (request.customerId() != null && !repository.customerExists(request.customerId()))
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Customer not found");
        if (request.carrierId() != null && !repository.carrierExists(request.carrierId()))
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Carrier not found");
        String fc = request.amazonFcCode().trim().toUpperCase(Locale.ROOT);
        return new WriteValues(request.customerId(), request.warehouseId(), fc,
            repository.amazonFcAddressId(fc), request.carrierId(), dateTime(request.scheduledPickupAt()),
            dateTime(request.appointmentTime()), clean(request.referenceNo()), clean(request.shipmentId()),
            clean(request.stNumber()), clean(request.remark()));
    }

    private boolean allowed(String mode, List<Long> ids, Long id, String role) {
        return "ADMIN".equals(role) || !"SELECTED".equals(mode) || (id != null && ids.contains(id));
    }
    private void requireWrite(UserAccount user) {
        if (user == null) throw new ApiException(HttpStatus.UNAUTHORIZED, "Not authenticated");
        if (!WRITE_ROLES.contains(user.role())) throw new ApiException(HttpStatus.FORBIDDEN, "Insufficient permissions");
    }
    private OffsetDateTime dateTime(String value) {
        if (value == null || value.isBlank()) return null;
        try { return OffsetDateTime.parse(value).atZoneSameInstant(BUSINESS_ZONE).toOffsetDateTime(); }
        catch (DateTimeException ignored) {
            try { return LocalDateTime.parse(value).atZone(BUSINESS_ZONE).toOffsetDateTime(); }
            catch (DateTimeException bad) { throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Invalid datetime"); }
        }
    }
    private String clean(String value) { return value == null ? null : value.trim(); }
    private boolean hasText(String value) { return value != null && !value.isBlank(); }
    private BigDecimal orAll(BigDecimal requested, BigDecimal current) { return requested == null ? current : requested; }
    private Quantities quantities(BigDecimal p, BigDecimal c, BigDecimal w, BigDecimal v) {
        Quantities q = new Quantities(zero(p), zero(c), zero(w), zero(v)); validateNonNegative(q); return q;
    }
    private BigDecimal zero(BigDecimal value) { return value == null ? BigDecimal.ZERO : value; }
    private void validateNonNegative(Quantities q) {
        if (q.pallet().signum()<0 || q.carton().signum()<0 || q.weight().signum()<0 || q.cbm().signum()<0)
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Quantities cannot be negative");
    }
    private void requirePositive(Quantities q, String message) {
        if (!q.anyPositive()) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, message);
    }

    static final class FcMismatchException extends RuntimeException {
        FcMismatchException(String message) { super(message); }
    }

    record Quantities(BigDecimal pallet, BigDecimal carton, BigDecimal weight, BigDecimal cbm) {
        Quantities plus(Quantities q) { return new Quantities(pallet.add(q.pallet), carton.add(q.carton), weight.add(q.weight), cbm.add(q.cbm)); }
        Quantities minus(Quantities q) { return new Quantities(pallet.subtract(q.pallet), carton.subtract(q.carton), weight.subtract(q.weight), cbm.subtract(q.cbm)); }
        Quantities negate() { return new Quantities(pallet.negate(), carton.negate(), weight.negate(), cbm.negate()); }
        boolean anyPositive() { return pallet.signum()>0 || carton.signum()>0 || weight.signum()>0 || cbm.signum()>0; }
        boolean exceeds(Quantities q) { return pallet.compareTo(q.pallet)>0 || carton.compareTo(q.carton)>0 || weight.compareTo(q.weight)>0 || cbm.compareTo(q.cbm)>0; }
    }

    record WriteValues(Long customerId, long warehouseId, String amazonFcCode, Long amazonFcAddressId,
                       Long carrierId, OffsetDateTime scheduledPickupAt, OffsetDateTime appointmentTime,
                       String referenceNo, String shipmentId, String stNumber, String remark) {}
}

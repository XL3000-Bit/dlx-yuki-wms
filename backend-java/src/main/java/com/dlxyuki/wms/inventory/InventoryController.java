package com.dlxyuki.wms.inventory;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.*;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@Validated
@RestController
@RequestMapping("/api/v1/inventory")
public class InventoryController {
    private final InventoryService service;
    public InventoryController(InventoryService service) { this.service = service; }

    @GetMapping
    InventoryListResponse list(
        @RequestParam(defaultValue="1") @Min(1) int page,
        @RequestParam(name="per_page", defaultValue="20") @Min(1) @Max(100) int perPage,
        @RequestParam(required=false) String q,
        @RequestParam(name="container_number", required=false) String containerNumber,
        @RequestParam(name="fc_code", required=false) String fcCode,
        @RequestParam(name="customer_id", required=false) Long customerId,
        @RequestParam(name="warehouse_id", required=false) Long warehouseId,
        @RequestParam(name="location_id", required=false) Long locationId,
        @RequestParam(required=false) Integer status,
        @RequestParam(name="priority_level", required=false) String priorityLevel,
        @RequestParam(name="inbound_date_from", required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate inboundDateFrom,
        @RequestParam(name="inbound_date_to", required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate inboundDateTo,
        @RequestParam(name="aging_min", required=false) @Min(0) Integer agingMin,
        @RequestParam(name="aging_max", required=false) @Min(0) Integer agingMax,
        @RequestParam(name="has_available", required=false) Boolean hasAvailable,
        @RequestParam(name="sort_by", defaultValue="id") String sortBy,
        @RequestParam(name="sort_order", defaultValue="desc") @Pattern(regexp="asc|desc") String sortOrder,
        @AuthenticationPrincipal UserAccount user) {
        return service.list(new InventoryQuery(page, perPage, q, containerNumber, fcCode, customerId,
            warehouseId, locationId, status, priorityLevel, inboundDateFrom, inboundDateTo,
            agingMin, agingMax, hasAvailable, sortBy, sortOrder), user);
    }

    @GetMapping("/{lotId}")
    InventoryResponse get(@PathVariable long lotId, @AuthenticationPrincipal UserAccount user) {
        return service.get(lotId, user);
    }

    @GetMapping("/{lotId}/transactions")
    List<InventoryTransactionResponse> transactions(@PathVariable long lotId,
        @AuthenticationPrincipal UserAccount user) {
        return service.transactions(lotId, user);
    }
}

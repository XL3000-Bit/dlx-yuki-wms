package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@Validated
@RestController
@RequestMapping("/api/v1/fba")
public class FbaController {
    private final FbaService service;
    public FbaController(FbaService service) { this.service = service; }

    @GetMapping
    Object list(@RequestParam(defaultValue="1") @Min(1) int page,
                @RequestParam(name="per_page", defaultValue="20") @Min(1) @Max(100) int perPage,
                @RequestParam(required=false) String q, @RequestParam(name="fba_no", required=false) String fbaNo,
                @RequestParam(name="customer_id", required=false) Long customerId, @RequestParam(name="warehouse_id", required=false) Long warehouseId,
                @RequestParam(name="amazon_fc_code", required=false) String amazonFcCode, @RequestParam(name="carrier_id", required=false) Long carrierId,
                @RequestParam(required=false) Integer status, @RequestParam(name="container_number", required=false) String containerNumber,
                @RequestParam(name="location_id", required=false) Long locationId, @RequestParam(name="priority_level", required=false) String priorityLevel,
                @RequestParam(name="aging_min", required=false) @Min(0) Integer agingMin, @RequestParam(name="aging_max", required=false) @Min(0) Integer agingMax,
                @RequestParam(name="appointment_from", required=false) String appointmentFrom, @RequestParam(name="appointment_to", required=false) String appointmentTo,
                @RequestParam(name="sort_by", defaultValue="id") String sortBy,
                @RequestParam(name="sort_order", defaultValue="desc") @Pattern(regexp="asc|desc") String sortOrder,
                @AuthenticationPrincipal UserAccount user) {
        return service.list(new FbaQuery(page, perPage, q, fbaNo, customerId, warehouseId, amazonFcCode, carrierId, status,
            containerNumber, locationId, priorityLevel, agingMin, agingMax, appointmentFrom, appointmentTo, sortBy, sortOrder), user);
    }

    @GetMapping("/workbench")
    Object workbench(@RequestParam(defaultValue="1") @Min(1) int page,
                     @RequestParam(name="per_page", defaultValue="20") @Min(1) @Max(100) int perPage,
                     @RequestParam(name="warehouse_id", required=false) Long warehouseId,
                     @RequestParam(name="customer_id", required=false) Long customerId,
                     @RequestParam(required=false) String q,
                     @RequestParam(defaultValue="all") String stage,
                     @RequestParam(required=false) String priority,
                     @RequestParam(name="only_old", defaultValue="false") boolean onlyOld,
                     @RequestParam(name="unload_from", required=false) String unloadFrom,
                     @RequestParam(name="unload_to", required=false) String unloadTo,
                     @RequestParam(name="aging_min", required=false) @Min(0) Integer agingMin,
                     @RequestParam(name="aging_max", required=false) @Min(0) Integer agingMax,
                     @RequestParam(name="sort_by", defaultValue="priority_rank") String sortBy,
                     @RequestParam(name="sort_order", defaultValue="desc") @Pattern(regexp="asc|desc") String sortOrder,
                     @RequestParam(name="amazon_fc_code", required=false) String amazonFcCode,
                     @RequestParam(name="container_number", required=false) String containerNumber,
                     @RequestParam(name="location_id", required=false) Long locationId,
                     @RequestParam(name="carrier_id", required=false) Long carrierId,
                     @RequestParam(name="fba_status", required=false) Integer fbaStatus,
                     @RequestParam(name="outbound_status", required=false) Integer outboundStatus,
                     @RequestParam(name="picking_status", required=false) Integer pickingStatus,
                     @RequestParam(name="bol_status", required=false) Integer bolStatus,
                     @RequestParam(name="st_number", required=false) String stNumber,
                     @RequestParam(name="po_number", required=false) String poNumber,
                     @RequestParam(name="scheduled_from", required=false) String scheduledFrom,
                     @RequestParam(name="scheduled_to", required=false) String scheduledTo,
                     @RequestParam(name="appointment_from", required=false) String appointmentFrom,
                     @RequestParam(name="appointment_to", required=false) String appointmentTo,
                     @AuthenticationPrincipal UserAccount user) {
        return service.workbench(new WorkbenchQuery(page, perPage, warehouseId, customerId, q, stage,
            priority, onlyOld, unloadFrom, unloadTo, agingMin, agingMax, amazonFcCode,
            containerNumber, locationId, carrierId, fbaStatus, outboundStatus, pickingStatus,
            bolStatus, stNumber, poNumber, scheduledFrom, scheduledTo, appointmentFrom,
            appointmentTo, sortBy, sortOrder), user);
    }

    @GetMapping("/{fba_id}/workbench-detail")
    Object workbenchDetail(@PathVariable("fba_id") long fbaId,
                           @AuthenticationPrincipal UserAccount user) {
        return service.workbenchDetail(fbaId, user);
    }

    @GetMapping("/{fba_id}")
    Object get(@PathVariable("fba_id") long fbaId, @AuthenticationPrincipal UserAccount user) {
        return service.get(fbaId, user);
    }
}

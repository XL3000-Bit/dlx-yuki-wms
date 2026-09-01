package com.dlxyuki.wms.inbound;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.*;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@Validated
@RestController
@RequestMapping("/api/v1/inbound")
public class InboundController {
    private final InboundService service;
    public InboundController(InboundService service) { this.service = service; }

    @GetMapping
    InboundListResponse list(
        @RequestParam(defaultValue="1") @Min(1) int page,
        @RequestParam(name="per_page",defaultValue="20") @Min(1) @Max(100) int perPage,
        @RequestParam(required=false) String q,
        @RequestParam(name="container_number",required=false) String containerNumber,
        @RequestParam(name="customer_id",required=false) Long customerId,
        @RequestParam(name="warehouse_id",required=false) Long warehouseId,
        @RequestParam(name="fc_code",required=false) String fcCode,
        @RequestParam(name="location_id",required=false) Long locationId,
        @RequestParam(required=false) @Min(0) @Max(5) Integer status,
        @RequestParam(name="unload_date_from",required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate unloadDateFrom,
        @RequestParam(name="unload_date_to",required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate unloadDateTo,
        @RequestParam(name="received_date_from",required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate receivedDateFrom,
        @RequestParam(name="received_date_to",required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate receivedDateTo,
        @RequestParam(name="sort_by",defaultValue="id") String sortBy,
        @RequestParam(name="sort_order",defaultValue="desc") @Pattern(regexp="asc|desc") String sortOrder,
        @AuthenticationPrincipal UserAccount user) {
        return service.list(new InboundQuery(page,perPage,q,containerNumber,customerId,warehouseId,fcCode,locationId,status,unloadDateFrom,unloadDateTo,receivedDateFrom,receivedDateTo,sortBy,sortOrder), user);
    }

    @GetMapping("/{recordId}")
    InboundResponse get(@PathVariable long recordId, @AuthenticationPrincipal UserAccount user) { return service.get(recordId, user); }

}

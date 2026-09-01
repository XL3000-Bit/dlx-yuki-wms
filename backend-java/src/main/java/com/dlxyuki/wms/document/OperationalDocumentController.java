package com.dlxyuki.wms.document;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/documents")
public class OperationalDocumentController {
    private final OperationalDocumentService service;
    public OperationalDocumentController(OperationalDocumentService service) { this.service = service; }

    @GetMapping
    Object list(@RequestParam(required=false) String q,
                @RequestParam(name="document_type",required=false) @Pattern(regexp="BOL|POD|DELIVERY_RECEIPT|WAREHOUSE|EXCEPTION_ATTACHMENT|GENERAL") String documentType,
                @RequestParam(required=false) @Pattern(regexp="DRAFT|AVAILABLE|SUPERSEDED|ARCHIVED") String status,
                @RequestParam(name="warehouse_id",required=false) Long warehouseId,
                @RequestParam(name="customer_id",required=false) Long customerId,
                @RequestParam(name="load_id",required=false) Long loadId,
                @RequestParam(name="outbound_id",required=false) Long outboundId,
                @RequestParam(name="bol_id",required=false) Long bolId,
                @RequestParam(name="work_order_id",required=false) Long workOrderId,
                @RequestParam(name="operational_exception_id",required=false) Long operationalExceptionId,
                @RequestParam(defaultValue="1") @Min(1) int page,
                @RequestParam(name="per_page",defaultValue="20") @Min(1) @Max(100) int perPage,
                @AuthenticationPrincipal UserAccount user) {
        return service.list(q,documentType,status,warehouseId,customerId,loadId,outboundId,bolId,workOrderId,operationalExceptionId,page,perPage,user);
    }

    @GetMapping("/{document_id}")
    Object detail(@PathVariable("document_id") long id,@AuthenticationPrincipal UserAccount user) { return service.detail(id,user); }

    @GetMapping("/{document_id}/events")
    Object events(@PathVariable("document_id") long id,@AuthenticationPrincipal UserAccount user) { return service.events(id,user); }
}

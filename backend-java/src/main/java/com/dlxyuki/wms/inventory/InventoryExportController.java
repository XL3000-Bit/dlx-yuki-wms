package com.dlxyuki.wms.inventory;

import com.dlxyuki.wms.user.UserAccount;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/inventory")
public class InventoryExportController {
    static final String XLSX_MEDIA_TYPE =
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    private final InventoryExportService service;

    public InventoryExportController(InventoryExportService service) { this.service = service; }

    @GetMapping("/files/export.xlsx")
    ResponseEntity<byte[]> export(@RequestParam(required = false) String q,
                                  @RequestParam(name = "container_number", required = false) String containerNumber,
                                  @RequestParam(name = "fc_code", required = false) String fcCode,
                                  @RequestParam(name = "customer_id", required = false) Long customerId,
                                  @RequestParam(name = "warehouse_id", required = false) Long warehouseId,
                                  @RequestParam(name = "location_id", required = false) Long locationId,
                                  @RequestParam(required = false) Integer status,
                                  @RequestParam(name = "priority_level", required = false) String priorityLevel,
                                  @RequestParam(name = "aging_min", required = false) Integer agingMin,
                                  @RequestParam(name = "aging_max", required = false) Integer agingMax,
                                  @AuthenticationPrincipal UserAccount user) {
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(XLSX_MEDIA_TYPE))
            .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=Inventory_Export.xlsx")
            .body(service.export(q, containerNumber, fcCode, customerId, warehouseId, locationId,
                status, priorityLevel, agingMin, agingMax, user));
    }
}

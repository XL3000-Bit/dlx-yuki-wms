package com.dlxyuki.wms.outbound;

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
@RequestMapping("/api/v1/outbounds")
public class OutboundExportController {
    static final String XLSX_MEDIA_TYPE =
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    private final OutboundExportService service;

    public OutboundExportController(OutboundExportService service) {
        this.service = service;
    }

    @GetMapping("/files/export.xlsx")
    ResponseEntity<byte[]> export(@RequestParam(required = false) String q,
                                  @RequestParam(required = false) Integer status,
                                  @RequestParam(name = "ob_type", required = false) String obType,
                                  @RequestParam(name = "warehouse_id", required = false) Long warehouseId,
                                  @AuthenticationPrincipal UserAccount user) {
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(XLSX_MEDIA_TYPE))
            .header(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=Outbound_Export.xlsx")
            .body(service.export(q, status, obType, warehouseId, user));
    }
}

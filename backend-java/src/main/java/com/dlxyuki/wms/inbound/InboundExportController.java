package com.dlxyuki.wms.inbound;

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
@RequestMapping("/api/v1/inbound")
public class InboundExportController {
    static final String XLSX_MEDIA_TYPE =
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    private final InboundExportService service;

    public InboundExportController(InboundExportService service) {
        this.service = service;
    }

    @GetMapping("/files/export.xlsx")
    ResponseEntity<byte[]> export(@RequestParam(required = false) String q,
                                  @RequestParam(name = "warehouse_id", required = false) Long warehouseId,
                                  @RequestParam(name = "fc_code", required = false) String fcCode,
                                  @AuthenticationPrincipal UserAccount user) {
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(XLSX_MEDIA_TYPE))
            .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=Inbound_Export.xlsx")
            .body(service.export(q, warehouseId, fcCode, user));
    }
}

package com.dlxyuki.wms.fba;

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
@RequestMapping("/api/v1/fba")
public class FbaExportController {
    static final String XLSX_MEDIA_TYPE =
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    private final FbaExportService service;

    public FbaExportController(FbaExportService service) {
        this.service = service;
    }

    @GetMapping("/files/export.xlsx")
    ResponseEntity<byte[]> export(@RequestParam(required = false) String q,
                                  @RequestParam(name = "warehouse_id", required = false) Long warehouseId,
                                  @RequestParam(name = "amazon_fc_code", required = false) String amazonFcCode,
                                  @RequestParam(required = false) Integer status,
                                  @RequestParam(name = "priority_level", required = false) String priorityLevel,
                                  @RequestParam(name = "selected_ids", required = false) String selectedIds,
                                  @AuthenticationPrincipal UserAccount user) {
        byte[] workbook = service.export(q, warehouseId, amazonFcCode, status,
            priorityLevel, selectedIds, user);
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(XLSX_MEDIA_TYPE))
            .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=FBA_Export.xlsx")
            .body(workbook);
    }
}

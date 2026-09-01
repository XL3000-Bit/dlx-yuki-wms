package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.user.UserAccount;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/fba")
public class FbaWorkbenchExportController {
    static final String XLSX_MEDIA_TYPE="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private final FbaWorkbenchExportService service;
    public FbaWorkbenchExportController(FbaWorkbenchExportService service){this.service=service;}

    @PostMapping("/workbench/export-selected")
    ResponseEntity<byte[]> exportSelected(@RequestBody(required=false) Map<String,Object> payload,
                                           @AuthenticationPrincipal UserAccount user){
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(XLSX_MEDIA_TYPE))
            .header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=FBA_Workbench_Selected.xlsx")
            .body(service.export(payload,user));
    }
}

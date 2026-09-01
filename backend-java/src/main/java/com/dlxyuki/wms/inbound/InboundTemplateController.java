package com.dlxyuki.wms.inbound;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/inbound")
public class InboundTemplateController {
    private final InboundTemplateService service;

    public InboundTemplateController(InboundTemplateService service) {
        this.service = service;
    }

    @GetMapping("/files/template.xlsx")
    ResponseEntity<byte[]> template() {
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(InboundExportController.XLSX_MEDIA_TYPE))
            .header(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=Inbound_Import_Template.xlsx")
            .body(service.template());
    }
}

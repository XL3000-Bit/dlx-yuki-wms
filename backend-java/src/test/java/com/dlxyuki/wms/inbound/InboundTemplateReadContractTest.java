package com.dlxyuki.wms.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.io.ByteArrayInputStream;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;

class InboundTemplateReadContractTest {
    @Test void exposesAuthenticatedStaticTemplateDownload() throws Exception {
        GetMapping mapping = InboundTemplateController.class.getDeclaredMethod("template")
            .getAnnotation(GetMapping.class);
        assertThat(mapping.value()).containsExactly("/files/template.xlsx");
        InboundTemplateService service = mock(InboundTemplateService.class);
        when(service.template()).thenReturn(new byte[] {1});
        var response = new InboundTemplateController(service).template();
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION))
            .isEqualTo("attachment; filename=Inbound_Import_Template.xlsx");
    }

    @Test void workbookHasExactSheetHeadersAndSample() throws Exception {
        byte[] bytes = new InboundTemplateService().template();
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            var sheet = workbook.getSheet("Inbound Import");
            assertThat(sheet.getPhysicalNumberOfRows()).isEqualTo(2);
            assertThat(InboundTemplateService.HEADERS).hasSize(13);
            for (int index = 0; index < 13; index++) {
                assertThat(sheet.getRow(0).getCell(index).getStringCellValue())
                    .isEqualTo(InboundTemplateService.HEADERS.get(index));
                assertThat(sheet.getRow(1).getCell(index).getStringCellValue())
                    .isEqualTo(InboundTemplateService.SAMPLE.get(index));
            }
        }
    }
}

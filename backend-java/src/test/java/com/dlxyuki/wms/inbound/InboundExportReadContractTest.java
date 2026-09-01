package com.dlxyuki.wms.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.inbound.InboundListResponse.PaginationMeta;
import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayInputStream;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class InboundExportReadContractTest {
    @Test void exposesTheStaticExportRouteAndDownloadHeaders() throws Exception {
        assertThat(InboundExportController.class.getAnnotation(RequestMapping.class).value())
            .containsExactly("/api/v1/inbound");
        GetMapping mapping = InboundExportController.class.getDeclaredMethod("export",
            String.class, Long.class, String.class, UserAccount.class).getAnnotation(GetMapping.class);
        assertThat(mapping.value()).containsExactly("/files/export.xlsx");
        InboundExportService service = mock(InboundExportService.class);
        when(service.export(any(), any(), any(), any())).thenReturn(new byte[] {1});
        var response = new InboundExportController(service).export(null, null, null, user());
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION))
            .isEqualTo("attachment; filename=Inbound_Export.xlsx");
    }

    @Test void exportsExactSeventeenColumnsAndStringQuantities() throws Exception {
        byte[] bytes = InboundExportService.workbook(List.of(record()));
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            var sheet = workbook.getSheet("Inbound");
            assertThat(sheet.getPhysicalNumberOfRows()).isEqualTo(2);
            assertThat(InboundExportService.HEADERS).hasSize(17);
            for (int index = 0; index < InboundExportService.HEADERS.size(); index++) {
                assertThat(sheet.getRow(0).getCell(index).getStringCellValue())
                    .isEqualTo(InboundExportService.HEADERS.get(index));
            }
            assertThat(sheet.getRow(1).getCell(8).getCellType()).isEqualTo(CellType.STRING);
            assertThat(sheet.getRow(1).getCell(8).getStringCellValue()).isEqualTo("12.50");
            assertThat(sheet.getRow(1).getCell(16).getLocalDateTimeCellValue())
                .isEqualTo(OffsetDateTime.parse("2026-08-31T09:30:00-07:00").toLocalDateTime());
        }
    }

    @Test void emptyFilterResultStillProducesAHeaderOnlyWorkbook() throws Exception {
        InboundService inbound = mock(InboundService.class);
        when(inbound.list(any(InboundQuery.class), any(UserAccount.class)))
            .thenReturn(new InboundListResponse(List.of(), new PaginationMeta(1, 100, 0, 0)));
        byte[] bytes = new InboundExportService(inbound).export("missing", 3L, "LAX9", user());
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            assertThat(workbook.getSheet("Inbound").getPhysicalNumberOfRows()).isEqualTo(1);
        }
    }

    private static InboundResponse record() {
        return new InboundResponse(1, "IB-1", "CONT-1",
            new InboundResponse.NamedRef(1, "C1", "Customer"),
            new InboundResponse.NamedRef(2, "WH1", "Warehouse"),
            new InboundResponse.NamedRef(3, "A01", "Location"),
            LocalDate.of(2026, 8, 28), LocalDate.of(2026, 8, 29), "LAX9", "M1",
            "12.50", "20.00", "100.00", "2.5000", 1, "Received", 3, "Remark",
            new InboundResponse.UserRef(1, "Tester"),
            OffsetDateTime.parse("2026-08-31T09:30:00-07:00"),
            OffsetDateTime.parse("2026-08-31T09:30:00-07:00"), false, null);
    }

    private static UserAccount user() {
        return new UserAccount(1, null, null, "tester", "Tester", null, "", "admin", true,
            "all", "all", List.of(), List.of());
    }
}

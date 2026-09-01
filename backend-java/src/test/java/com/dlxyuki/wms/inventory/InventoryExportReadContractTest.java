package com.dlxyuki.wms.inventory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.inventory.InventoryListResponse.PaginationMeta;
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

class InventoryExportReadContractTest {
    @Test void exposesStaticRouteAndExactDownloadHeaders() throws Exception {
        assertThat(InventoryExportController.class.getAnnotation(RequestMapping.class).value())
            .containsExactly("/api/v1/inventory");
        GetMapping mapping = InventoryExportController.class.getDeclaredMethod("export",
            String.class, String.class, String.class, Long.class, Long.class, Long.class,
            Integer.class, String.class, Integer.class, Integer.class, UserAccount.class)
            .getAnnotation(GetMapping.class);
        assertThat(mapping.value()).containsExactly("/files/export.xlsx");
        InventoryExportService service = mock(InventoryExportService.class);
        when(service.export(any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any()))
            .thenReturn(new byte[] {1});
        var response = new InventoryExportController(service).export(null, null, null, null, null,
            null, null, null, null, null, user());
        assertThat(response.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION))
            .isEqualTo("attachment; filename=Inventory_Export.xlsx");
    }

    @Test void exportsTwentyColumnsWithStringQuantities() throws Exception {
        byte[] bytes = InventoryExportService.workbook(List.of(record()));
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            var sheet = workbook.getSheet("Inventory");
            assertThat(InventoryExportService.HEADERS).hasSize(20);
            for (int i = 0; i < InventoryExportService.HEADERS.size(); i++)
                assertThat(sheet.getRow(0).getCell(i).getStringCellValue()).isEqualTo(InventoryExportService.HEADERS.get(i));
            assertThat(sheet.getRow(1).getCell(10).getCellType()).isEqualTo(CellType.STRING);
            assertThat(sheet.getRow(1).getCell(10).getStringCellValue()).isEqualTo("10.50");
        }
    }

    @Test void emptyResultProducesHeaderOnlyWorkbook() throws Exception {
        InventoryService inventory = mock(InventoryService.class);
        when(inventory.list(any(InventoryQuery.class), any(UserAccount.class)))
            .thenReturn(new InventoryListResponse(List.of(), new PaginationMeta(1, 100, 0, 0)));
        byte[] bytes = new InventoryExportService(inventory).export(null, null, null, null, null,
            null, null, null, null, null, user());
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            assertThat(workbook.getSheet("Inventory").getPhysicalNumberOfRows()).isEqualTo(1);
        }
    }

    private static InventoryResponse record() {
        var customer = new InventoryResponse.NamedRef(1, "C1", "Customer");
        var warehouse = new InventoryResponse.NamedRef(2, "WH1", "Warehouse");
        var location = new InventoryResponse.NamedRef(3, "A01", "Location");
        return new InventoryResponse(1, "LOT-1", "CONT-1", "LAX9", "M", customer, warehouse,
            location, 9, LocalDate.of(2026, 8, 1), 31, "HIGH", "High", "10.50", "8.00",
            "2.50", "0.00", "20.00", "15.00", "5.00", "0.00", "100.00", "80.00",
            "20.00", "2.00", "1.50", "0.50", 1, "Available", "Remark",
            OffsetDateTime.now(), OffsetDateTime.now());
    }

    private static UserAccount user() {
        return new UserAccount(1, null, null, "tester", "Tester", null, "", "admin", true,
            "all", "all", List.of(), List.of());
    }
}

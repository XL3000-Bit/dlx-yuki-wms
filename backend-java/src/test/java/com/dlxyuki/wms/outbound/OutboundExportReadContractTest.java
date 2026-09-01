package com.dlxyuki.wms.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayInputStream;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class OutboundExportReadContractTest {
    @Test void exposesOnlyTheStaticFastApiExportGet() throws Exception {
        RequestMapping root = OutboundExportController.class.getAnnotation(RequestMapping.class);
        assertThat(root.value()).containsExactly("/api/v1/outbounds");
        GetMapping mapping = OutboundExportController.class.getDeclaredMethod("export",
            String.class, Integer.class, String.class, Long.class, UserAccount.class)
            .getAnnotation(GetMapping.class);
        assertThat(mapping.value()).containsExactly("/files/export.xlsx");
        assertThat(Arrays.stream(OutboundExportController.class.getDeclaredMethods())
            .noneMatch(method -> method.isAnnotationPresent(PostMapping.class)
                || method.isAnnotationPresent(PutMapping.class)
                || method.isAnnotationPresent(PatchMapping.class)
                || method.isAnnotationPresent(DeleteMapping.class))).isTrue();
    }

    @Test void writesExactHeadersNamesAndStringQuantities() throws Exception {
        byte[] bytes = OutboundExportService.workbook(List.of(record()));
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            var sheet = workbook.getSheet("Outbound");
            assertThat(sheet.getPhysicalNumberOfRows()).isEqualTo(2);
            assertThat(OutboundExportService.HEADERS).containsExactly(
                "OB#", "Status", "OB Type", "Carrier", "Warehouse", "Pallet", "Carton",
                "Weight LBS", "CBM", "Reference");
            for (int index = 0; index < OutboundExportService.HEADERS.size(); index++) {
                assertThat(sheet.getRow(0).getCell(index).getStringCellValue())
                    .isEqualTo(OutboundExportService.HEADERS.get(index));
            }
            assertThat(sheet.getRow(1).getCell(3).getStringCellValue()).isEmpty();
            assertThat(sheet.getRow(1).getCell(4).getStringCellValue()).isEqualTo("Los Angeles");
            for (int index = 5; index <= 8; index++) {
                assertThat(sheet.getRow(1).getCell(index).getCellType()).isEqualTo(CellType.STRING);
            }
            assertThat(sheet.getRow(1).getCell(5).getStringCellValue()).isEqualTo("12.50");
        }
    }

    @Test void usesListOutboundFiltersScopeAndTenThousandRowPage() throws Exception {
        OutboundRepository repository = mock(OutboundRepository.class);
        when(repository.list(any(OutboundQuery.class), any(UserAccount.class))).thenReturn(Map.of(
            "data", List.of(),
            "meta", Map.of("page", 1, "per_page", 10_000, "total", 0, "total_pages", 0)));
        OutboundExportService service = new OutboundExportService(repository);
        UserAccount user = user();

        byte[] bytes = service.export("needle", 3, "FBA", 9L, user);

        ArgumentCaptor<OutboundQuery> query = ArgumentCaptor.forClass(OutboundQuery.class);
        org.mockito.Mockito.verify(repository).list(query.capture(), org.mockito.Mockito.eq(user));
        assertThat(query.getValue()).satisfies(value -> {
            assertThat(value.page()).isEqualTo(1);
            assertThat(value.perPage()).isEqualTo(10_000);
            assertThat(value.q()).isEqualTo("needle");
            assertThat(value.status()).isEqualTo(3);
            assertThat(value.obType()).isEqualTo("FBA");
            assertThat(value.warehouseId()).isEqualTo(9L);
        });
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            assertThat(workbook.getSheet("Outbound").getPhysicalNumberOfRows()).isEqualTo(1);
        }
    }

    @Test void controllerReturnsRequiredDownloadHeaders() {
        OutboundExportService service = mock(OutboundExportService.class);
        when(service.export(any(), any(), any(), any(), any())).thenReturn(new byte[]{1});
        var response = new OutboundExportController(service)
            .export(null, null, null, null, user());
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getHeaders().getContentType().toString())
            .isEqualTo(OutboundExportController.XLSX_MEDIA_TYPE);
        assertThat(response.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION))
            .isEqualTo("attachment; filename=Outbound_Export.xlsx");
    }

    private static Map<String, Object> record() {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("ob_no", "OB-20"); row.put("status_name", "Confirmed");
        row.put("ob_type", "FBA"); row.put("carrier", null);
        row.put("warehouse", Map.of("name", "Los Angeles"));
        row.put("total_pallet_qty", "12.50"); row.put("total_carton_qty", "24.00");
        row.put("total_weight_lbs", "1800.00"); row.put("total_cbm", "3.2500");
        row.put("reference_no", "REF-20");
        return row;
    }

    private static UserAccount user() {
        return new UserAccount(1, null, null, "tester", "Tester", null, "", "admin", true,
            "all", "all", List.of(), List.of());
    }
}

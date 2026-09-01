package com.dlxyuki.wms.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
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
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class OutboundWorkbenchExportContractTest {
    @Test void exposesTheExactSelectedExportPost() {
        RequestMapping root = OutboundWorkbenchExportController.class
            .getAnnotation(RequestMapping.class);
        assertThat(root.value()).containsExactly("/api/v1/outbounds");
        PostMapping mapping = Arrays.stream(
                OutboundWorkbenchExportController.class.getDeclaredMethods())
            .filter(method -> method.isAnnotationPresent(PostMapping.class))
            .findFirst().orElseThrow().getAnnotation(PostMapping.class);
        assertThat(mapping.value()).containsExactly("/workbench/export-selected");
    }

    @Test void fetchesTheFullWorkbenchThenFiltersInMemoryWithoutReordering()
        throws Exception {
        OutboundRepository repository = mock(OutboundRepository.class);
        Map<String, Object> first = row(8L, "OB-8");
        Map<String, Object> second = row(5L, "OB-5");
        Map<String, Object> hidden = row(3L, "OB-3");
        when(repository.workbench(any(WorkbenchQuery.class), any(UserAccount.class)))
            .thenReturn(Map.of("data", List.of(first, second, hidden)));
        OutboundWorkbenchExportService service =
            new OutboundWorkbenchExportService(repository);

        byte[] bytes = service.export(Map.of("ids", List.of(5, 8, 99)), user());

        ArgumentCaptor<WorkbenchQuery> query =
            ArgumentCaptor.forClass(WorkbenchQuery.class);
        verify(repository).workbench(query.capture(), any(UserAccount.class));
        assertThat(query.getValue()).satisfies(value -> {
            assertThat(value.page()).isEqualTo(1);
            assertThat(value.perPage()).isEqualTo(10_000);
            assertThat(value.sortBy()).isEqualTo("created_at");
            assertThat(value.sortOrder()).isEqualTo("desc");
        });
        try (XSSFWorkbook workbook =
                 new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            var sheet = workbook.getSheet("Outbound");
            assertThat(sheet.getPhysicalNumberOfRows()).isEqualTo(3);
            assertThat(sheet.getRow(1).getCell(0).getStringCellValue())
                .isEqualTo("OB-8");
            assertThat(sheet.getRow(2).getCell(0).getStringCellValue())
                .isEqualTo("OB-5");
        }
    }

    @Test void writesExact16ColumnsAndStringQuantities() throws Exception {
        byte[] bytes = OutboundWorkbenchExportService.workbook(
            List.of(row(8L, "OB-8")));
        try (XSSFWorkbook workbook =
                 new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            var sheet = workbook.getSheet("Outbound");
            assertThat(OutboundWorkbenchExportService.HEADERS).containsExactly(
                "OB#", "Status", "Carrier", "FBA", "ST", "FC", "Planned PLT",
                "Allocated PLT", "Picked PLT", "Completed PLT", "Remaining PLT",
                "Weight LB", "CBM", "Schedule PU", "APT", "Reference");
            assertThat(sheet.getRow(0).getLastCellNum()).isEqualTo((short) 16);
            for (int column = 6; column <= 12; column++) {
                assertThat(sheet.getRow(1).getCell(column).getCellType())
                    .isEqualTo(CellType.STRING);
            }
        }
    }

    @Test void treatsMissingEmptyOrNonnumericIdsAsAnEmptySelection() {
        assertThat(OutboundWorkbenchExportService.ids(null)).isEmpty();
        assertThat(OutboundWorkbenchExportService.ids(Map.of())).isEmpty();
        assertThat(OutboundWorkbenchExportService.ids(
            Map.of("ids", List.of()))).isEmpty();
        assertThat(OutboundWorkbenchExportService.ids(
            Map.of("ids", List.of(7, "bad")))).isEmpty();
        assertThat(OutboundWorkbenchExportService.ids(
            Map.of("ids", List.of("8", 9)))).containsExactly(8L, 9L);
    }

    @Test void controllerReturnsRequiredDownloadHeaders() {
        OutboundWorkbenchExportService service =
            mock(OutboundWorkbenchExportService.class);
        when(service.export(any(), any())).thenReturn(new byte[]{1});
        var response = new OutboundWorkbenchExportController(service)
            .exportSelected(Map.of(), user());
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getHeaders().getContentType().toString())
            .isEqualTo(OutboundWorkbenchExportController.XLSX_MEDIA_TYPE);
        assertThat(response.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION))
            .isEqualTo("attachment; filename=Outbound_Selected.xlsx");
    }

    private static Map<String, Object> row(long id, String obNo) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", id); row.put("ob_no", obNo);
        row.put("status_name", "Confirmed"); row.put("carrier", "Carrier");
        row.put("fba_no", "FBA-1"); row.put("st_number", "ST-1");
        row.put("fc_code", "LAX9"); row.put("planned_pallet_qty", "12.50");
        row.put("allocated_pallet_qty", "10.00");
        row.put("picked_pallet_qty", "8.00");
        row.put("completed_pallet_qty", "6.00");
        row.put("remaining_pallet_qty", "4.00");
        row.put("allocated_weight_lbs", "1800.00");
        row.put("allocated_cbm", "3.2500");
        row.put("schedule_pickup_at", "2026-09-01T08:00:00");
        row.put("delivery_appointment_time", "2026-09-02T09:00:00");
        row.put("reference_no", "REF-1");
        return row;
    }

    private static UserAccount user() {
        return new UserAccount(1, null, null, "tester", "Tester", null, "",
            "admin", true, "all", "all", List.of(), List.of());
    }
}

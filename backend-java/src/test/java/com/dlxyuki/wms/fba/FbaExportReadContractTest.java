package com.dlxyuki.wms.fba;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayInputStream;
import java.time.OffsetDateTime;
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

class FbaExportReadContractTest {
    @Test void exposesOnlyTheStaticFastApiExportGet() throws Exception {
        RequestMapping root = FbaExportController.class.getAnnotation(RequestMapping.class);
        assertThat(root.value()).containsExactly("/api/v1/fba");
        GetMapping mapping = FbaExportController.class.getDeclaredMethod("export",
            String.class, Long.class, String.class, Integer.class, String.class, String.class,
            UserAccount.class).getAnnotation(GetMapping.class);
        assertThat(mapping.value()).containsExactly("/files/export.xlsx");
        assertThat(Arrays.stream(FbaExportController.class.getDeclaredMethods())
            .noneMatch(method -> method.isAnnotationPresent(PostMapping.class)
                || method.isAnnotationPresent(PutMapping.class)
                || method.isAnnotationPresent(PatchMapping.class)
                || method.isAnnotationPresent(DeleteMapping.class))).isTrue();
    }

    @Test void writesExactHeadersStringQuantitiesAndTimezoneFreeDates() throws Exception {
        Map<String, Object> record = record(7L, "FBA-007");
        record.put("scheduled_pickup_at", OffsetDateTime.parse("2026-08-31T09:30:00-07:00"));
        byte[] bytes = FbaExportService.workbook(List.of(record));

        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            var sheet = workbook.getSheet("FBA");
            assertThat(sheet.getPhysicalNumberOfRows()).isEqualTo(2);
            assertThat(FbaExportService.HEADERS).containsExactly(
                "FBA No", "Amazon FC", "FC Address", "Customer", "Containers", "Pallet",
                "Carton", "Weight", "CBM", "Oldest Inbound Date", "Aging", "Priority",
                "Warehouse", "Carrier", "Schedule PU", "APT Time", "ST Number", "Status");
            for (int index = 0; index < FbaExportService.HEADERS.size(); index++) {
                assertThat(sheet.getRow(0).getCell(index).getStringCellValue())
                    .isEqualTo(FbaExportService.HEADERS.get(index));
            }
            assertThat(sheet.getRow(1).getCell(5).getCellType()).isEqualTo(CellType.STRING);
            assertThat(sheet.getRow(1).getCell(5).getStringCellValue()).isEqualTo("12.50");
            assertThat(sheet.getRow(1).getCell(14).getLocalDateTimeCellValue())
                .isEqualTo(OffsetDateTime.parse("2026-08-31T09:30:00-07:00").toLocalDateTime());
        }
    }

    @Test void filtersSelectedIdsAfterUsingTheListFbaFilters() throws Exception {
        FbaRepository repository = mock(FbaRepository.class);
        when(repository.list(any(FbaQuery.class), any(UserAccount.class))).thenReturn(Map.of(
            "data", List.of(record(7L, "FBA-007"), record(8L, "FBA-008")),
            "meta", Map.of("total_pages", 1)));
        FbaExportService service = new FbaExportService(repository);

        byte[] bytes = service.export("needle", 3L, "LAX9", 2, "HIGH", "8, bad", user());

        ArgumentCaptor<FbaQuery> query = ArgumentCaptor.forClass(FbaQuery.class);
        org.mockito.Mockito.verify(repository).list(query.capture(), any(UserAccount.class));
        assertThat(query.getValue()).satisfies(value -> {
            assertThat(value.q()).isEqualTo("needle");
            assertThat(value.warehouseId()).isEqualTo(3L);
            assertThat(value.amazonFcCode()).isEqualTo("LAX9");
            assertThat(value.status()).isEqualTo(2);
            assertThat(value.priorityLevel()).isEqualTo("HIGH");
            assertThat(value.page()).isEqualTo(1);
            assertThat(value.perPage()).isEqualTo(100);
        });
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            assertThat(workbook.getSheet("FBA").getPhysicalNumberOfRows()).isEqualTo(2);
            assertThat(workbook.getSheet("FBA").getRow(1).getCell(0).getStringCellValue())
                .isEqualTo("FBA-008");
        }
        assertThat(FbaExportService.selectedIds("8, bad, 009")).containsExactly(8L, 9L);
    }

    @Test void controllerReturnsRequiredDownloadHeaders() {
        FbaExportService service = mock(FbaExportService.class);
        when(service.export(any(), any(), any(), any(), any(), any(), any())).thenReturn(new byte[]{1});
        var response = new FbaExportController(service)
            .export(null, null, null, null, null, null, user());
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getHeaders().getContentType().toString())
            .isEqualTo(FbaExportController.XLSX_MEDIA_TYPE);
        assertThat(response.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION))
            .isEqualTo("attachment; filename=FBA_Export.xlsx");
    }

    private static Map<String, Object> record(long id, String number) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", id); row.put("fba_no", number); row.put("amazon_fc_code", "LAX9");
        row.put("amazon_fc_address", "123 Main St");
        row.put("customer", Map.of("name", "Customer")); row.put("containers", List.of("CONT1"));
        row.put("total_pallet_qty", "12.50"); row.put("total_carton_qty", "24.00");
        row.put("total_weight_lbs", "1800.00"); row.put("total_cbm", "3.2500");
        row.put("oldest_inbound_date", "2026-08-01"); row.put("max_aging_days", 30);
        row.put("priority_level", "HIGH"); row.put("priority_label", "High");
        row.put("warehouse", Map.of("code", "WH1")); row.put("carrier", Map.of("name", "Carrier"));
        row.put("scheduled_pickup_at", ""); row.put("appointment_time", "");
        row.put("st_number", "ST-1"); row.put("status_name", "Allocated");
        return row;
    }

    private static UserAccount user() {
        return new UserAccount(1, null, null, "tester", "Tester", null, "", "admin", true,
            "all", "all", List.of(), List.of());
    }
}

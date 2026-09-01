package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

@Service
public class FbaExportService {
    static final List<String> HEADERS = List.of(
        "FBA No", "Amazon FC", "FC Address", "Customer", "Containers", "Pallet",
        "Carton", "Weight", "CBM", "Oldest Inbound Date", "Aging", "Priority",
        "Warehouse", "Carrier", "Schedule PU", "APT Time", "ST Number", "Status");

    private final FbaRepository repository;

    public FbaExportService(FbaRepository repository) {
        this.repository = repository;
    }

    byte[] export(String q, Long warehouseId, String amazonFcCode, Integer status,
                  String priorityLevel, String selectedIds, UserAccount user) {
        List<Map<String, Object>> records = allRows(q, warehouseId, amazonFcCode, status,
            priorityLevel, user);
        Set<Long> wanted = selectedIds(selectedIds);
        if (selectedIds != null && !selectedIds.isBlank()) {
            records.removeIf(row -> !wanted.contains(((Number) row.get("id")).longValue()));
        }
        return workbook(records);
    }

    private List<Map<String, Object>> allRows(String q, Long warehouseId,
                                               String amazonFcCode, Integer status,
                                               String priorityLevel, UserAccount user) {
        List<Map<String, Object>> records = new ArrayList<>();
        int page = 1;
        long totalPages;
        do {
            FbaQuery query = new FbaQuery(page, 100, q, null, null, warehouseId,
                amazonFcCode, null, status, null, null, priorityLevel, null, null,
                null, null, "id", "desc");
            Map<String, Object> result = repository.list(query, user);
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> data = (List<Map<String, Object>>) result.get("data");
            @SuppressWarnings("unchecked")
            Map<String, Object> meta = (Map<String, Object>) result.get("meta");
            records.addAll(data);
            totalPages = ((Number) meta.get("total_pages")).longValue();
            page++;
        } while (page <= totalPages);
        return records;
    }

    static Set<Long> selectedIds(String value) {
        Set<Long> ids = new LinkedHashSet<>();
        if (value == null) return ids;
        Arrays.stream(value.split(","))
            .map(String::trim)
            .filter(part -> part.matches("\\d+"))
            .map(Long::valueOf)
            .forEach(ids::add);
        return ids;
    }

    static byte[] workbook(List<Map<String, Object>> records) {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("FBA");
            Row header = sheet.createRow(0);
            for (int i = 0; i < HEADERS.size(); i++) {
                header.createCell(i).setCellValue(HEADERS.get(i));
            }
            int rowIndex = 1;
            for (Map<String, Object> record : records) {
                Row row = sheet.createRow(rowIndex++);
                List<Object> values = List.of(
                    text(record.get("fba_no")), text(record.get("amazon_fc_code")),
                    text(record.get("amazon_fc_address")), refName(record.get("customer")),
                    String.join(", ", strings(record.get("containers"))),
                    text(record.get("total_pallet_qty")), text(record.get("total_carton_qty")),
                    text(record.get("total_weight_lbs")), text(record.get("total_cbm")),
                    nullable(record.get("oldest_inbound_date")), nullable(record.get("max_aging_days")),
                    priority(record), refCode(record.get("warehouse")), refName(record.get("carrier")),
                    nullable(record.get("scheduled_pickup_at")), nullable(record.get("appointment_time")),
                    text(record.get("st_number")), text(record.get("status_name")));
                for (int i = 0; i < values.size(); i++) write(row.createCell(i), values.get(i));
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to generate FBA export", exception);
        }
    }

    private static String priority(Map<String, Object> row) {
        return (text(row.get("priority_level")) + " " + text(row.get("priority_label"))).trim();
    }

    private static Object nullable(Object value) { return value == null ? "" : value; }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }

    @SuppressWarnings("unchecked")
    private static String refName(Object value) {
        return value instanceof Map<?, ?> map ? text(map.get("name")) : "";
    }

    private static String refCode(Object value) {
        return value instanceof Map<?, ?> map ? text(map.get("code")) : "";
    }

    private static List<String> strings(Object value) {
        if (!(value instanceof List<?> list)) return List.of();
        return list.stream().map(FbaExportService::text).toList();
    }

    private static void write(Cell cell, Object value) {
        if (value instanceof OffsetDateTime dateTime) {
            cell.setCellValue(dateTime.toLocalDateTime());
        } else if (value instanceof ZonedDateTime dateTime) {
            cell.setCellValue(dateTime.toLocalDateTime());
        } else if (value instanceof LocalDateTime dateTime) {
            cell.setCellValue(dateTime);
        } else if (value instanceof LocalDate date) {
            cell.setCellValue(date);
        } else if (value instanceof Number number) {
            cell.setCellValue(number.doubleValue());
        } else {
            cell.setCellValue(text(value));
        }
    }
}

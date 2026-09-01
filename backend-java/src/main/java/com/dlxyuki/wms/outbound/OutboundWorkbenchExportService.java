package com.dlxyuki.wms.outbound;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
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
public class OutboundWorkbenchExportService {
    static final List<String> HEADERS = List.of(
        "OB#", "Status", "Carrier", "FBA", "ST", "FC", "Planned PLT",
        "Allocated PLT", "Picked PLT", "Completed PLT", "Remaining PLT",
        "Weight LB", "CBM", "Schedule PU", "APT", "Reference");

    private final OutboundRepository repository;

    public OutboundWorkbenchExportService(OutboundRepository repository) {
        this.repository = repository;
    }

    byte[] export(Map<String, Object> payload, UserAccount user) {
        Set<Long> selectedIds = ids(payload);
        WorkbenchQuery query = new WorkbenchQuery(1, 10_000, null, null, null,
            null, null, "created_at", "desc");
        @SuppressWarnings("unchecked")
        Map<String, Object> result =
            (Map<String, Object>) repository.workbench(query, user);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> rows =
            (List<Map<String, Object>>) result.get("data");
        List<Map<String, Object>> selectedRows = rows == null ? List.of() : rows.stream()
            .filter(row -> selectedIds.contains(rowId(row.get("id"))))
            .toList();
        return workbook(selectedRows);
    }

    static Set<Long> ids(Map<String, Object> payload) {
        if (payload == null || !(payload.get("ids") instanceof List<?> values)) {
            return Set.of();
        }
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Object value : values) {
            Long id = rowId(value);
            if (id == null) {
                return Set.of();
            }
            ids.add(id);
        }
        return ids;
    }

    static byte[] workbook(List<Map<String, Object>> records) {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("Outbound");
            Row header = sheet.createRow(0);
            for (int index = 0; index < HEADERS.size(); index++) {
                header.createCell(index).setCellValue(HEADERS.get(index));
            }
            int rowIndex = 1;
            for (Map<String, Object> record : records) {
                Row row = sheet.createRow(rowIndex++);
                List<Object> values = List.of(
                    text(record.get("ob_no")), text(record.get("status_name")),
                    text(record.get("carrier")), text(record.get("fba_no")),
                    text(record.get("st_number")), text(record.get("fc_code")),
                    text(record.get("planned_pallet_qty")),
                    text(record.get("allocated_pallet_qty")),
                    text(record.get("picked_pallet_qty")),
                    text(record.get("completed_pallet_qty")),
                    text(record.get("remaining_pallet_qty")),
                    text(record.get("allocated_weight_lbs")),
                    text(record.get("allocated_cbm")),
                    nullable(record.get("schedule_pickup_at")),
                    nullable(record.get("delivery_appointment_time")),
                    text(record.get("reference_no")));
                for (int column = 0; column < values.size(); column++) {
                    write(row.createCell(column), values.get(column));
                }
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new IllegalStateException(
                "Unable to generate outbound workbench export", exception);
        }
    }

    private static Long rowId(Object value) {
        if (value instanceof Byte || value instanceof Short
            || value instanceof Integer || value instanceof Long) {
            return ((Number) value).longValue();
        }
        if (value instanceof String text && text.trim().matches("[+-]?\\d+")) {
            try {
                return Long.valueOf(text.trim());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private static Object nullable(Object value) {
        return value == null ? "" : value;
    }

    private static String text(Object value) {
        return value == null ? "" : String.valueOf(value);
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
        } else {
            cell.setCellValue(text(value));
        }
    }
}

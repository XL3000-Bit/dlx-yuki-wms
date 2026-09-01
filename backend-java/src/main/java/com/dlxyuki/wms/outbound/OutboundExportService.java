package com.dlxyuki.wms.outbound;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

@Service
public class OutboundExportService {
    static final List<String> HEADERS = List.of(
        "OB#", "Status", "OB Type", "Carrier", "Warehouse", "Pallet", "Carton",
        "Weight LBS", "CBM", "Reference");

    private final OutboundRepository repository;

    public OutboundExportService(OutboundRepository repository) {
        this.repository = repository;
    }

    byte[] export(String q, Integer status, String obType, Long warehouseId,
                  UserAccount user) {
        OutboundQuery query = new OutboundQuery(1, 10_000, q, null, status, obType,
            null, warehouseId, null, null, null, null, null, "id", "desc");
        @SuppressWarnings("unchecked")
        Map<String, Object> result = (Map<String, Object>) repository.list(query, user);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> rows = (List<Map<String, Object>>) result.get("data");
        return workbook(rows);
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
                List<String> values = List.of(
                    text(record.get("ob_no")), text(record.get("status_name")),
                    text(record.get("ob_type")), refName(record.get("carrier")),
                    refName(record.get("warehouse")), text(record.get("total_pallet_qty")),
                    text(record.get("total_carton_qty")), text(record.get("total_weight_lbs")),
                    text(record.get("total_cbm")), text(record.get("reference_no")));
                for (int index = 0; index < values.size(); index++) {
                    row.createCell(index).setCellValue(values.get(index));
                }
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to generate outbound export", exception);
        }
    }

    private static String text(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static String refName(Object value) {
        return value instanceof Map<?, ?> map ? text(map.get("name")) : "";
    }
}

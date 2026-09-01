package com.dlxyuki.wms.inbound;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

@Service
public class InboundExportService {
    static final List<String> HEADERS = List.of(
        "Inbound No", "Container Number", "Customer", "Warehouse", "Unload Date",
        "Received Date", "FC Code", "Marking", "Pallet Qty", "Carton Qty",
        "Weight LBS", "CBM", "Location", "Status", "Aging Days", "Remark", "Created At");

    private final InboundService inboundService;

    public InboundExportService(InboundService inboundService) {
        this.inboundService = inboundService;
    }

    byte[] export(String q, Long warehouseId, String fcCode, UserAccount user) {
        List<InboundResponse> records = new ArrayList<>();
        int page = 1;
        long totalPages;
        do {
            InboundQuery query = new InboundQuery(page, 100, q, null, null, warehouseId,
                fcCode, null, null, null, null, null, null, "id", "desc");
            InboundListResponse response = inboundService.list(query, user);
            records.addAll(response.data());
            totalPages = response.meta().totalPages();
            page++;
        } while (page <= totalPages);
        return workbook(records);
    }

    static byte[] workbook(List<InboundResponse> records) {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("Inbound");
            Row header = sheet.createRow(0);
            for (int index = 0; index < HEADERS.size(); index++) {
                header.createCell(index).setCellValue(HEADERS.get(index));
            }
            int rowIndex = 1;
            for (InboundResponse record : records) {
                Row row = sheet.createRow(rowIndex++);
                Object[] values = {
                    record.inboundNo(), record.containerNumber(), name(record.customer()),
                    name(record.warehouse()), record.unloadDate(), record.receivedDate(),
                    record.fcCode(), record.marking(), record.palletQty(), record.cartonQty(),
                    record.weightLbs(), record.cbm(), code(record.location()), record.statusName(),
                    record.agingDays(), record.remark(), record.createdAt()
                };
                for (int index = 0; index < values.length; index++) {
                    write(row.createCell(index), values[index]);
                }
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to generate inbound export", exception);
        }
    }

    private static String name(InboundResponse.NamedRef ref) { return ref == null ? "" : ref.name(); }
    private static String code(InboundResponse.NamedRef ref) { return ref == null ? "" : ref.code(); }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }

    private static void write(Cell cell, Object value) {
        if (value instanceof OffsetDateTime dateTime) cell.setCellValue(dateTime.toLocalDateTime());
        else if (value instanceof LocalDateTime dateTime) cell.setCellValue(dateTime);
        else if (value instanceof LocalDate date) cell.setCellValue(date);
        else if (value instanceof Number number) cell.setCellValue(number.doubleValue());
        else cell.setCellValue(text(value));
    }
}

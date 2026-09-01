package com.dlxyuki.wms.inbound;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

@Service
public class InboundTemplateService {
    static final List<String> HEADERS = List.of(
        "Container Number", "Customer", "Warehouse", "Unload Date", "Received Date",
        "FC Code", "Marking", "Pallet Qty", "Carton Qty", "Weight LBS", "CBM",
        "Location", "Remark");
    static final List<String> SAMPLE = List.of(
        "MSCU1234567", "ACME", "DLX-LAX", "2026-08-28", "2026-08-29", "LAX9",
        "FBA-001", "10", "200", "12500", "42.5", "A01", "Example row");

    byte[] template() {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("Inbound Import");
            Row header = sheet.createRow(0);
            Row sample = sheet.createRow(1);
            for (int index = 0; index < HEADERS.size(); index++) {
                header.createCell(index).setCellValue(HEADERS.get(index));
                sample.createCell(index).setCellValue(SAMPLE.get(index));
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to generate inbound template", exception);
        }
    }
}

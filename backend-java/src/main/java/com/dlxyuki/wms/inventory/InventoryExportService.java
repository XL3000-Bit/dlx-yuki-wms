package com.dlxyuki.wms.inventory;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

@Service
public class InventoryExportService {
    static final List<String> HEADERS = List.of(
        "Lot No", "Container Number", "FC Code", "Marking", "Customer", "Warehouse",
        "Location", "Inbound Date", "Aging Days", "Priority", "Original Pallet",
        "Available Pallet", "Allocated Pallet", "Hold Pallet", "Original Carton",
        "Available Carton", "Weight LBS", "CBM", "Status", "Remark");

    private final InventoryService inventoryService;

    public InventoryExportService(InventoryService inventoryService) { this.inventoryService = inventoryService; }

    byte[] export(String q, String containerNumber, String fcCode, Long customerId,
                  Long warehouseId, Long locationId, Integer status, String priorityLevel,
                  Integer agingMin, Integer agingMax, UserAccount user) {
        List<InventoryResponse> records = new ArrayList<>();
        int page = 1;
        long totalPages;
        do {
            InventoryQuery query = new InventoryQuery(page, 100, q, containerNumber, fcCode,
                customerId, warehouseId, locationId, status, priorityLevel, null, null,
                agingMin, agingMax, null, "id", "desc");
            InventoryListResponse response = inventoryService.list(query, user);
            records.addAll(response.data());
            totalPages = response.meta().totalPages();
            page++;
        } while (page <= totalPages);
        return workbook(records);
    }

    static byte[] workbook(List<InventoryResponse> records) {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("Inventory");
            Row header = sheet.createRow(0);
            for (int i = 0; i < HEADERS.size(); i++) header.createCell(i).setCellValue(HEADERS.get(i));
            int rowIndex = 1;
            for (InventoryResponse item : records) {
                Row row = sheet.createRow(rowIndex++);
                String priority = String.join(" ", text(item.priorityLevel()), text(item.priorityLabel())).trim();
                String[] values = {
                    item.lotNo(), item.containerNumber(), item.fcCode(), item.marking(), name(item.customer()),
                    code(item.warehouse()), code(item.location()), text(item.inboundDate()), text(item.agingDays()),
                    priority, item.originalPalletQty(), item.availablePalletQty(), item.allocatedPalletQty(),
                    item.holdPalletQty(), item.originalCartonQty(), item.availableCartonQty(),
                    item.availableWeightLbs(), item.availableCbm(), item.statusName(), item.remark()
                };
                for (int i = 0; i < values.length; i++) row.createCell(i).setCellValue(text(values[i]));
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to generate inventory export", exception);
        }
    }

    private static String code(InventoryResponse.NamedRef ref) { return ref == null ? "" : text(ref.code()); }
    private static String name(InventoryResponse.NamedRef ref) { return ref == null ? "" : text(ref.name()); }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }
}

package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.user.UserAccount;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

@Service
public class FbaWorkbenchExportService {
    static final List<String> HEADERS = List.of(
        "FBA No", "ST Number", "PO", "Container", "FC", "Location", "Pallet",
        "Carton", "Weight LB", "CBM", "Inbound Date", "Warehouse Days",
        "Inventory Priority", "Earliest Outbound", "Days Remaining",
        "Dispatch Priority", "Warehouse", "Carrier", "Schedule PU", "APT Time",
        "Picking No", "BOL No", "Outbound No", "Stage");

    private final FbaRepository repository;

    public FbaWorkbenchExportService(FbaRepository repository) { this.repository=repository; }

    byte[] export(Map<String,Object> payload,UserAccount user){
        List<Long> ids=fbaIds(payload);
        WorkbenchQuery query=new WorkbenchQuery(1,10000,null,null,null,"all",null,false,
            null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,
            null,null,"id","asc");
        Map<String,Object> result=repository.workbench(query,user,ids);
        @SuppressWarnings("unchecked") List<Map<String,Object>> rows=(List<Map<String,Object>>)result.get("data");
        return workbook(rows==null?List.of():rows);
    }

    static List<Long> fbaIds(Map<String,Object> payload){
        if(payload==null||!(payload.get("fba_ids") instanceof List<?> values))return List.of();
        LinkedHashSet<Long> ids=new LinkedHashSet<>();
        for(Object value:values){
            Long id=parseId(value);
            if(id==null)return List.of();
            ids.add(id);
        }
        return new ArrayList<>(ids);
    }

    private static Long parseId(Object value){
        if(value instanceof Byte||value instanceof Short||value instanceof Integer||value instanceof Long)return ((Number)value).longValue();
        if(value instanceof String text&&text.trim().matches("[+-]?\\d+")){
            try{return Long.valueOf(text.trim());}catch(NumberFormatException ignored){return null;}
        }
        return null;
    }

    static byte[] workbook(List<Map<String,Object>> records){
        try(XSSFWorkbook workbook=new XSSFWorkbook();ByteArrayOutputStream output=new ByteArrayOutputStream()){
            Sheet sheet=workbook.createSheet("FBA Workbench");Row header=sheet.createRow(0);
            for(int i=0;i<HEADERS.size();i++)header.createCell(i).setCellValue(HEADERS.get(i));
            int index=1;
            for(Map<String,Object> record:records){
                Row row=sheet.createRow(index++);
                List<Object> values=List.of(
                    text(record.get("fba_no")),text(record.get("st_number")),text(record.get("po_number")),
                    join(record.get("containers_preview")),text(record.get("amazon_fc_code")),join(record.get("locations_preview")),
                    text(record.get("total_pallet_qty")),text(record.get("total_carton_qty")),text(record.get("total_weight_lbs")),text(record.get("total_cbm")),
                    nullable(record.get("oldest_inbound_date")),nullable(record.get("warehouse_days")),text(record.get("priority_label")),
                    nullable(record.get("earliest_outbound_date")),nullable(record.get("outbound_days_remaining")),text(record.get("dispatch_priority")),
                    text(record.get("warehouse")),text(record.get("carrier")),nullable(record.get("scheduled_pickup_at")),nullable(record.get("appointment_time")),
                    text(record.get("picking_no")),text(record.get("bol_no")),text(record.get("outbound_no")),text(record.get("workbench_stage_name")));
                for(int i=0;i<values.size();i++)write(row.createCell(i),values.get(i));
            }
            workbook.write(output);return output.toByteArray();
        }catch(IOException exception){throw new IllegalStateException("Unable to generate FBA workbench export",exception);}
    }

    private static Object nullable(Object value){return value==null?"":value;}
    private static String text(Object value){return value==null?"":String.valueOf(value);}
    private static String join(Object value){if(!(value instanceof List<?> list))return "";return String.join("; ",list.stream().map(FbaWorkbenchExportService::text).toList());}
    private static void write(Cell cell,Object value){
        if(value instanceof OffsetDateTime dateTime)cell.setCellValue(dateTime.toLocalDateTime());
        else if(value instanceof ZonedDateTime dateTime)cell.setCellValue(dateTime.toLocalDateTime());
        else if(value instanceof LocalDateTime dateTime)cell.setCellValue(dateTime);
        else if(value instanceof LocalDate date)cell.setCellValue(date);
        else if(value instanceof Number number)cell.setCellValue(number.doubleValue());
        else cell.setCellValue(text(value));
    }
}

package com.dlxyuki.wms.fba;

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

class FbaWorkbenchExportContractTest {
    @Test void exposesTheExactSelectedExportPost(){
        RequestMapping root=FbaWorkbenchExportController.class.getAnnotation(RequestMapping.class);
        assertThat(root.value()).containsExactly("/api/v1/fba");
        PostMapping mapping=Arrays.stream(FbaWorkbenchExportController.class.getDeclaredMethods())
            .filter(method->method.isAnnotationPresent(PostMapping.class)).findFirst().orElseThrow()
            .getAnnotation(PostMapping.class);
        assertThat(mapping.value()).containsExactly("/workbench/export-selected");
    }

    @Test void usesTheWorkbenchQueryWithIdsAndRequiredOrdering() throws Exception{
        FbaRepository repository=mock(FbaRepository.class);
        when(repository.workbench(any(WorkbenchQuery.class),any(UserAccount.class),any()))
            .thenReturn(Map.of("data",List.of(row())));
        FbaWorkbenchExportService service=new FbaWorkbenchExportService(repository);
        byte[] bytes=service.export(Map.of("fba_ids",List.of(9,7)),user());

        ArgumentCaptor<WorkbenchQuery> query=ArgumentCaptor.forClass(WorkbenchQuery.class);
        @SuppressWarnings("unchecked") ArgumentCaptor<java.util.Collection<Long>> ids=ArgumentCaptor.forClass(java.util.Collection.class);
        verify(repository).workbench(query.capture(),any(UserAccount.class),ids.capture());
        assertThat(query.getValue()).satisfies(value->{
            assertThat(value.page()).isEqualTo(1);assertThat(value.perPage()).isEqualTo(10000);
            assertThat(value.stage()).isEqualTo("all");assertThat(value.sortBy()).isEqualTo("id");
            assertThat(value.sortOrder()).isEqualTo("asc");
        });
        assertThat(ids.getValue()).containsExactly(9L,7L);
        try(XSSFWorkbook workbook=new XSSFWorkbook(new ByteArrayInputStream(bytes))){
            assertThat(workbook.getSheet("FBA Workbench").getPhysicalNumberOfRows()).isEqualTo(2);
        }
    }

    @Test void writesExact24ColumnsJoinedPreviewsAndStringQuantities() throws Exception{
        byte[] bytes=FbaWorkbenchExportService.workbook(List.of(row()));
        try(XSSFWorkbook workbook=new XSSFWorkbook(new ByteArrayInputStream(bytes))){
            var sheet=workbook.getSheet("FBA Workbench");
            assertThat(FbaWorkbenchExportService.HEADERS).containsExactly(
                "FBA No","ST Number","PO","Container","FC","Location","Pallet","Carton",
                "Weight LB","CBM","Inbound Date","Warehouse Days","Inventory Priority",
                "Earliest Outbound","Days Remaining","Dispatch Priority","Warehouse","Carrier",
                "Schedule PU","APT Time","Picking No","BOL No","Outbound No","Stage");
            assertThat(sheet.getRow(0).getLastCellNum()).isEqualTo((short)24);
            assertThat(sheet.getRow(1).getCell(3).getStringCellValue()).isEqualTo("CONT1; CONT2");
            assertThat(sheet.getRow(1).getCell(5).getStringCellValue()).isEqualTo("A01; B02");
            for(int column=6;column<=9;column++)assertThat(sheet.getRow(1).getCell(column).getCellType()).isEqualTo(CellType.STRING);
        }
    }

    @Test void treatsMissingEmptyOrNonnumericIdsAsAnEmptySelection(){
        assertThat(FbaWorkbenchExportService.fbaIds(null)).isEmpty();
        assertThat(FbaWorkbenchExportService.fbaIds(Map.of())).isEmpty();
        assertThat(FbaWorkbenchExportService.fbaIds(Map.of("fba_ids",List.of()))).isEmpty();
        assertThat(FbaWorkbenchExportService.fbaIds(Map.of("fba_ids",List.of(7,"bad")))).isEmpty();
        assertThat(FbaWorkbenchExportService.fbaIds(Map.of("fba_ids",List.of("8",9)))).containsExactly(8L,9L);
    }

    @Test void controllerReturnsRequiredDownloadHeaders(){
        FbaWorkbenchExportService service=mock(FbaWorkbenchExportService.class);
        when(service.export(any(),any())).thenReturn(new byte[]{1});
        var response=new FbaWorkbenchExportController(service).exportSelected(Map.of(),user());
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getHeaders().getContentType().toString()).isEqualTo(FbaWorkbenchExportController.XLSX_MEDIA_TYPE);
        assertThat(response.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION)).isEqualTo("attachment; filename=FBA_Workbench_Selected.xlsx");
    }

    private static Map<String,Object> row(){
        Map<String,Object> row=new LinkedHashMap<>();
        row.put("fba_no","FBA-7");row.put("st_number","ST-7");row.put("po_number","PO-7");
        row.put("containers_preview",List.of("CONT1","CONT2"));row.put("amazon_fc_code","LAX9");
        row.put("locations_preview",List.of("A01","B02"));row.put("total_pallet_qty","12.50");
        row.put("total_carton_qty","24.00");row.put("total_weight_lbs","1800.00");row.put("total_cbm","3.2500");
        row.put("oldest_inbound_date","2026-08-01");row.put("warehouse_days",31);row.put("priority_label","Old");
        row.put("earliest_outbound_date","2026-09-02");row.put("outbound_days_remaining",1);row.put("dispatch_priority","HIGH");
        row.put("warehouse","WH1");row.put("carrier","Carrier");row.put("scheduled_pickup_at","");row.put("appointment_time","");
        row.put("picking_no","PK-1");row.put("bol_no","BOL-1");row.put("outbound_no","OB-1");row.put("workbench_stage_name","Waiting Outbound");
        return row;
    }

    private static UserAccount user(){return new UserAccount(1,null,null,"tester","Tester",null,"","admin",true,"all","all",List.of(),List.of());}
}

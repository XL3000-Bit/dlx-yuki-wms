package com.dlxyuki.wms.imports;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.util.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/imports")
public class ImportReadController {
    public record Profile(String code,String name,String module,String sheetName) { }
    private static final List<Profile> PROFILES=List.of(
        new Profile("WEST_COAST_4_0_OL","West Coast 4.0 OL","INBOUND","OL"),
        new Profile("WEST_COAST_4_0_DS","West Coast 4.0 DS","FBA","DS"),
        new Profile("WEST_COAST_4_0_OUTBOUND","West Coast 4.0 Outbound","OUTBOUND","出库")
    );
    private final ImportReadRepository repository;
    ImportReadController(ImportReadRepository repository){this.repository=repository;}

    @GetMapping("/profiles")
    List<Profile> profiles(@AuthenticationPrincipal UserAccount user){return PROFILES;}
    @GetMapping
    List<ImportJobResponse> jobs(@AuthenticationPrincipal UserAccount user){return repository.list();}
    @GetMapping("/{jobId}")
    ImportJobResponse job(@PathVariable long jobId,@AuthenticationPrincipal UserAccount user){
        return repository.find(jobId).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"Import job not found"));
    }

    @GetMapping("/{jobId}/progress")
    Map<String,Object> progress(@PathVariable long jobId,@AuthenticationPrincipal UserAccount user){
        ImportJobResponse job=required(jobId); Map<String,Object> result=new LinkedHashMap<>();
        result.put("job_id",job.id()); result.put("status",job.status()); result.put("current_stage",job.currentStage());
        result.put("processed_rows",job.processedRows()); result.put("total_rows",job.totalRows());
        result.put("progress_percent",job.progressPercent()); result.put("warning_rows",job.warningRows());
        result.put("error_rows",job.errorRows()); return result;
    }

    @GetMapping("/{jobId}/validation-result")
    Map<String,Object> validationResult(@PathVariable long jobId,@AuthenticationPrincipal UserAccount user){
        ImportJobResponse job=required(jobId);
        if(!Set.of("READY","VALIDATED","COMPLETED").contains(job.status()))
            throw new ApiException(HttpStatus.CONFLICT,"Validation is not complete");
        List<Map<String,Object>> errors=repository.errors(jobId);
        Map<Integer,List<Map<String,Object>>> byRow=new HashMap<>();
        for(Map<String,Object> error:errors){
            Map<String,Object> issue=new LinkedHashMap<>(); issue.put("severity",error.get("severity"));
            issue.put("column",Optional.ofNullable(error.get("column_name")).orElse(""));
            issue.put("code",error.get("error_code")); issue.put("message",error.get("error_message"));
            byRow.computeIfAbsent((Integer)error.get("row_number"),key->new ArrayList<>()).add(issue);
        }
        List<Map<String,Object>> rows=new ArrayList<>();
        for(Map<String,Object> row:repository.rowsForValidation(jobId)){
            Map<String,Object> output=new LinkedHashMap<>(row);
            output.put("issues",byRow.getOrDefault((Integer)row.get("row_number"),List.of())); rows.add(output);
        }
        Map<String,Object> perf=job.performance()==null?Map.of():job.performance(); Map<String,Object> result=new LinkedHashMap<>();
        result.put("job_id",job.id()); result.put("total_rows",job.totalRows()); result.put("valid_rows",job.validRows());
        result.put("warning_rows",job.warningRows()); result.put("error_rows",job.errorRows()); result.put("rows",rows);
        result.put("duration_seconds",perf.get("validation_seconds")); result.put("rows_per_second",perf.get("validation_rows_per_second"));
        return result;
    }

    @GetMapping("/{jobId}/errors")
    List<Map<String,Object>> errors(@PathVariable long jobId,@AuthenticationPrincipal UserAccount user){required(jobId);return repository.errors(jobId);}

    @GetMapping("/{jobId}/rows")
    List<Map<String,Object>> rows(@PathVariable long jobId,@AuthenticationPrincipal UserAccount user){required(jobId);return repository.rows(jobId);}

    @GetMapping("/{jobId}/errors.xlsx")
    ResponseEntity<byte[]> errorExport(@PathVariable long jobId,@AuthenticationPrincipal UserAccount user){
        required(jobId); List<Map<String,Object>> errors=repository.errors(jobId);
        Map<Integer,Map<String,Object>> raw=repository.rawByRow(jobId);
        try(var workbook=new XSSFWorkbook();var output=new ByteArrayOutputStream()){
            var sheet=workbook.createSheet("Errors"); var header=sheet.createRow(0);
            String[] columns={"Row Number","Original Data","Error Code","Error Message","Suggested Fix"};
            for(int i=0;i<columns.length;i++)header.createCell(i).setCellValue(columns[i]);
            ObjectMapper json=new ObjectMapper(); int index=1;
            for(Map<String,Object> error:errors){var row=sheet.createRow(index++); int number=(Integer)error.get("row_number");
                row.createCell(0).setCellValue(number); row.createCell(1).setCellValue(json.writeValueAsString(raw.getOrDefault(number,Map.of())));
                row.createCell(2).setCellValue(Objects.toString(error.get("error_code"),""));
                row.createCell(3).setCellValue(Objects.toString(error.get("error_message"),""));
                row.createCell(4).setCellValue(Objects.toString(error.get("suggested_fix"),""));
            }
            workbook.write(output);
            return ResponseEntity.ok().contentType(MediaType.parseMediaType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=\"import-"+jobId+"-errors.xlsx\"").body(output.toByteArray());
        }catch(Exception exception){throw new IllegalStateException("Could not create import error workbook",exception);}
    }

    private ImportJobResponse required(long id){
        return repository.find(id).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"Import job not found"));
    }
}

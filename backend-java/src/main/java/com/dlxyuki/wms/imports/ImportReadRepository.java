package com.dlxyuki.wms.imports;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ImportReadRepository {
    private static final String SELECT = """
        select id,module,file_name,original_file_name,status,total_rows,processed_rows,
               progress_percent,current_stage,valid_rows,warning_rows,error_rows,imported_rows,
               created_by,created_at,completed_at,mapping,profile_code,source_sheet,file_hash,
               performance,reconciliation
          from import_jobs
        """;
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    public ImportReadRepository(JdbcTemplate jdbc, ObjectMapper json) { this.jdbc=jdbc; this.json=json; }

    public List<ImportJobResponse> list() {
        return jdbc.query(SELECT + " order by id desc limit 200", this::map);
    }
    public Optional<ImportJobResponse> find(long id) {
        return jdbc.query(SELECT + " where id=?", this::map, id).stream().findFirst();
    }
    public List<Map<String,Object>> rowsForValidation(long jobId) {
        return jdbc.query("""
            select row_number,mapped_data,validation_status from import_rows
             where import_job_id=? order by row_number limit 50
            """,(r,n)->Map.of("row_number",r.getInt("row_number"),
                "data",Optional.ofNullable(object(r,"mapped_data")).orElseGet(Map::of),
                "status",r.getString("validation_status")),jobId);
    }
    public List<Map<String,Object>> errors(long jobId) {
        return jdbc.query("""
            select id,row_number,column_name,raw_value,severity,error_code,error_message,suggested_fix,created_at
              from import_errors where import_job_id=? order by row_number,id
            """,(r,n)->{
                Map<String,Object> value=new LinkedHashMap<>();
                value.put("id",r.getLong("id")); value.put("row_number",r.getInt("row_number"));
                value.put("column_name",r.getString("column_name")); value.put("raw_value",r.getString("raw_value"));
                value.put("severity",r.getString("severity")); value.put("error_code",r.getString("error_code"));
                value.put("error_message",r.getString("error_message")); value.put("suggested_fix",r.getString("suggested_fix"));
                value.put("created_at",time(r,"created_at")); return value;
            },jobId);
    }
    public List<Map<String,Object>> rows(long jobId) {
        return jdbc.query("""
            select id,row_number,raw_data,mapped_data,validation_status,created_entity_type,created_entity_id,created_at
              from import_rows where import_job_id=? order by row_number limit 500
            """,(r,n)->{
                Map<String,Object> value=new LinkedHashMap<>();
                value.put("id",r.getLong("id")); value.put("row_number",r.getInt("row_number"));
                value.put("raw_data",Optional.ofNullable(object(r,"raw_data")).orElseGet(Map::of));
                value.put("mapped_data",object(r,"mapped_data")); value.put("validation_status",r.getString("validation_status"));
                value.put("created_entity_type",r.getString("created_entity_type"));
                Object entityId=r.getObject("created_entity_id"); value.put("created_entity_id",entityId==null?null:((Number)entityId).longValue());
                value.put("created_at",time(r,"created_at")); return value;
            },jobId);
    }
    public Map<Integer,Map<String,Object>> rawByRow(long jobId) {
        Map<Integer,Map<String,Object>> values=new HashMap<>();
        jdbc.query("select row_number,raw_data from import_rows where import_job_id=?",r->{
            values.put(r.getInt("row_number"),Optional.ofNullable(object(r,"raw_data")).orElseGet(Map::of));
        },jobId);
        return values;
    }
    private ImportJobResponse map(ResultSet r, int row) throws SQLException {
        String status=r.getString("status");
        return new ImportJobResponse(r.getLong("id"),r.getString("module"),r.getString("file_name"),
            r.getString("original_file_name"),status,r.getLong("total_rows"),r.getLong("processed_rows"),
            r.getBigDecimal("progress_percent")==null?0:r.getBigDecimal("progress_percent").doubleValue(),
            r.getString("current_stage"),r.getLong("valid_rows"),r.getLong("warning_rows"),r.getLong("error_rows"),
            r.getLong("imported_rows"),r.getLong("created_by"),time(r,"created_at"),time(r,"completed_at"),
            object(r,"mapping"),r.getString("profile_code"),r.getString("source_sheet"),r.getString("file_hash"),
            object(r,"performance"),object(r,"reconciliation"),title(status));
    }
    private OffsetDateTime time(ResultSet r,String key) throws SQLException {
        try { return r.getObject(key,OffsetDateTime.class); }
        catch (SQLException e) { Timestamp value=r.getTimestamp(key); return value==null?null:value.toInstant().atOffset(ZoneOffset.UTC); }
    }
    private Map<String,Object> object(ResultSet r,String key) throws SQLException {
        String value=r.getString(key); if(value==null)return null;
        try{return json.readValue(value,new TypeReference<>(){});}catch(Exception e){throw new SQLException("Invalid JSON in "+key,e);}
    }
    static String title(String value) {
        if(value==null)return null;
        StringJoiner result=new StringJoiner(" ");
        for(String part:value.toLowerCase(Locale.ROOT).split("_"))
            result.add(part.isEmpty()?part:Character.toUpperCase(part.charAt(0))+part.substring(1));
        return result.toString();
    }
}

package com.dlxyuki.wms.document;

import com.dlxyuki.wms.user.UserAccount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class OperationalDocumentRepository {
    private final NamedParameterJdbcTemplate jdbc;
    OperationalDocumentRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc=jdbc; }

    Map<String,Object> list(String q,String type,String status,Long warehouseId,Long customerId,Long loadId,Long outboundId,Long bolId,Long workOrderId,Long exceptionId,int page,int perPage,UserAccount user) {
        var p=new MapSqlParameterSource(); StringBuilder where=new StringBuilder(" where 1=1"); scope(where,p,user);
        if(q!=null&&!q.isBlank()){where.append(" and (d.document_no ilike :q or d.original_filename ilike :q or d.title ilike :q)");p.addValue("q","%"+q.strip()+"%");}
        eq(where,p,"document_type",type,"d.document_type::text"); eq(where,p,"status",status,"d.status::text");
        eq(where,p,"warehouse_id",warehouseId,"d.warehouse_id"); eq(where,p,"customer_id",customerId,"d.customer_id");
        eq(where,p,"load_id",loadId,"d.load_id"); eq(where,p,"outbound_id",outboundId,"d.outbound_id"); eq(where,p,"bol_id",bolId,"d.bol_id");
        eq(where,p,"work_order_id",workOrderId,"d.work_order_id"); eq(where,p,"exception_id",exceptionId,"d.operational_exception_id");
        long total=jdbc.queryForObject("select count(*) from operational_documents d"+where,p,Long.class);
        p.addValue("limit",perPage).addValue("offset",(page-1)*perPage);
        List<Map<String,Object>> data=jdbc.query("select d.* from operational_documents d"+where+" order by d.created_at desc,d.id desc limit :limit offset :offset",p,(r,n)->row(r));
        Map<String,Object> meta=new LinkedHashMap<>();meta.put("page",page);meta.put("per_page",perPage);meta.put("total",total);meta.put("total_pages",(total+perPage-1)/perPage);
        return Map.of("data",data,"meta",meta);
    }

    Optional<Map<String,Object>> find(long id,UserAccount user) {
        var p=new MapSqlParameterSource("id",id);StringBuilder where=new StringBuilder(" where d.id=:id");scope(where,p,user);
        return jdbc.query("select d.* from operational_documents d"+where,p,(r,n)->row(r)).stream().findFirst();
    }

    Optional<DocumentDownload> findDownload(long id,UserAccount user) {
        var p=new MapSqlParameterSource("id",id);StringBuilder where=new StringBuilder(" where d.id=:id");scope(where,p,user);
        return jdbc.query("select d.original_filename,d.content_type,d.storage_key,d.is_generated,d.bol_id from operational_documents d"+where,p,(r,n)->new DocumentDownload(r.getString("original_filename"),r.getString("content_type"),r.getString("storage_key"),r.getBoolean("is_generated"),nullableLong(r,"bol_id"))).stream().findFirst();
    }

    List<Map<String,Object>> events(long id) {
        return jdbc.query("select * from document_events where document_id=:id order by created_at desc,id desc",Map.of("id",id),(r,n)->{
            Map<String,Object> m=new LinkedHashMap<>();m.put("id",r.getLong("id"));m.put("document_id",r.getLong("document_id"));m.put("event_type",r.getString("event_type"));m.put("actor_user_id",nullableLong(r,"actor_user_id"));m.put("message",r.getString("message"));m.put("created_at",time(r,"created_at"));return m;
        });
    }

    private static void scope(StringBuilder w,MapSqlParameterSource p,UserAccount u){
        if(!"ADMIN".equals(u.role())&&"SELECTED".equals(u.warehouseScopeMode())){w.append(" and d.warehouse_id in (:warehouse_ids)");p.addValue("warehouse_ids",safe(u.warehouseIds()));}
        if(!"ADMIN".equals(u.role())&&"SELECTED".equals(u.customerScopeMode())){w.append(" and d.customer_id in (:customer_ids)");p.addValue("customer_ids",safe(u.customerIds()));}
    }
    private static List<Long> safe(List<Long> ids){return ids==null||ids.isEmpty()?List.of(-1L):ids;}
    private static void eq(StringBuilder w,MapSqlParameterSource p,String key,Object value,String column){if(value!=null){w.append(" and ").append(column).append(" = :").append(key);p.addValue(key,value);}}
    private static Map<String,Object> row(ResultSet r)throws SQLException{
        Map<String,Object> m=new LinkedHashMap<>();m.put("id",r.getLong("id"));m.put("document_no",r.getString("document_no"));m.put("document_type",r.getString("document_type"));m.put("status",r.getString("status"));m.put("version",r.getInt("version"));m.put("original_filename",r.getString("original_filename"));m.put("content_type",r.getString("content_type"));m.put("file_size",nullableLong(r,"file_size"));m.put("checksum_sha256",r.getString("checksum_sha256"));m.put("is_generated",r.getBoolean("is_generated"));m.put("title",r.getString("title"));m.put("notes",r.getString("notes"));m.put("warehouse_id",r.getLong("warehouse_id"));m.put("customer_id",nullableLong(r,"customer_id"));m.put("load_id",nullableLong(r,"load_id"));m.put("outbound_id",nullableLong(r,"outbound_id"));m.put("bol_id",nullableLong(r,"bol_id"));m.put("work_order_id",nullableLong(r,"work_order_id"));m.put("operational_exception_id",nullableLong(r,"operational_exception_id"));m.put("container_tracking_id",nullableLong(r,"container_tracking_id"));m.put("created_by",r.getLong("created_by"));m.put("archived_at",time(r,"archived_at"));m.put("archived_by",nullableLong(r,"archived_by"));m.put("created_at",time(r,"created_at"));m.put("updated_at",time(r,"updated_at"));return m;
    }
    private static Long nullableLong(ResultSet r,String c)throws SQLException{long v=r.getLong(c);return r.wasNull()?null:v;}
    private static Object time(ResultSet r,String c)throws SQLException{var t=r.getTimestamp(c);return t==null?null:t.toInstant().atOffset(ZoneOffset.UTC);}
}

record DocumentDownload(String originalFilename,String contentType,String storageKey,boolean generated,Long bolId) {}

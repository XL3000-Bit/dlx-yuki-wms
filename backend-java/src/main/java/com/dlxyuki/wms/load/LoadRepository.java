package com.dlxyuki.wms.load;

import com.dlxyuki.wms.user.UserAccount;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class LoadRepository {
    private final NamedParameterJdbcTemplate jdbc;
    LoadRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }

    Object list(int page, int size, String q, String status, Long warehouseId, LocalDate from, LocalDate to, UserAccount user) {
        MapSqlParameterSource p = new MapSqlParameterSource(); List<String> filters = new ArrayList<>(); scope(user,p,filters,"l.warehouse_id");
        if (q != null && !q.isEmpty()) { p.addValue("q", "%" + q.trim() + "%"); filters.add("l.load_no ilike :q"); }
        exact(filters,p,"status",status,"l.status::text"); exact(filters,p,"warehouse_id",warehouseId,"l.warehouse_id");
        if (from != null) { p.addValue("from",from.atStartOfDay()); filters.add("l.appointment_time>=:from"); }
        if (to != null) { p.addValue("to",to.atTime(LocalTime.MAX)); filters.add("l.appointment_time<:to"); }
        List<Long> ids=jdbc.query("select l.id from loads l"+where(filters)+" order by l.id desc",p,(r,n)->r.getLong(1));
        int total=ids.size(), start=Math.min((page-1)*size,total), end=Math.min(start+size,total); List<Map<String,Object>> data=new ArrayList<>();
        for(Long id:ids.subList(start,end)) data.add(read(id));
        Map<String,Object> out=new LinkedHashMap<>();out.put("data",data);out.put("meta",meta(page,size,total));return out;
    }

    Optional<Map<String,Object>> find(long id, UserAccount user) {
        MapSqlParameterSource p=new MapSqlParameterSource("id",id);List<String> f=new ArrayList<>(List.of("l.id=:id"));scope(user,p,f,"l.warehouse_id");
        return jdbc.query("select l.id from loads l"+where(f),p,(r,n)->read(r.getLong(1))).stream().findFirst();
    }

    private Map<String,Object> read(long id) {
        Map<String,Object>x=jdbc.queryForObject("""
            select l.*,w.warehouse_code,w.warehouse_name,c.carrier_code,c.carrier_name
            from loads l join warehouses w on w.id=l.warehouse_id left join carriers c on c.id=l.carrier_id where l.id=:id
            """,Map.of("id",id),(r,n)->loadRow(r));
        List<Map<String,Object>> outbounds=jdbc.query("""
            select o.id,o.ob_no,o.fc_code,o.status,f.fba_no,
              coalesce(sum(a.allocated_pallet_qty-a.completed_pallet_qty),0) pallet_qty,
              coalesce(sum(a.allocated_carton_qty-a.completed_carton_qty),0) carton_qty,
              coalesce(sum(a.allocated_weight_lbs-a.completed_weight_lbs),0) weight_lbs,
              coalesce(sum(a.allocated_cbm-a.completed_cbm),0) cbm
            from outbound_orders o left join fba_shipments f on f.id=o.fba_shipment_id
            left join outbound_inventory_allocations a on a.outbound_order_id=o.id where o.load_id=:id
            group by o.id,o.ob_no,o.fc_code,o.status,f.fba_no order by o.id
            """,Map.of("id",id),(r,n)->outbound(r));
        List<Map<String,Object>> workOrders=jdbc.query("""
            select wo.*,u.display_name assignee_name from work_orders wo left join users u on u.id=wo.assigned_to where wo.load_id=:id order by wo.id
            """,Map.of("id",id),(r,n)->workOrder(r));
        List<Map<String,Object>> exceptions=jdbc.query("""
            select id,exception_no,severity::text severity,status::text status,title from operational_exceptions
            where load_id=:id and status::text in ('OPEN','INVESTIGATING') order by id
            """,Map.of("id",id),(r,n)->exception(r));
        x.put("outbound_count",outbounds.size()); x.put("total_pallet_qty",sum(outbounds,"pallet_qty"));x.put("total_carton_qty",sum(outbounds,"carton_qty"));x.put("total_weight_lbs",sum(outbounds,"weight_lbs"));x.put("total_cbm",sum(outbounds,"cbm"));
        x.put("outbounds",outbounds);x.put("work_orders",workOrders);x.put("active_exception_count",exceptions.size());x.put("active_exceptions",exceptions.subList(0,Math.min(5,exceptions.size())));return x;
    }

    Map<String,Object> executionSummary(long id) {
        boolean hasStageTransactions=tableExists("stage_transactions");
        boolean hasVerificationTransactions=tableExists("load_verification_transactions");
        List<Map<String,Object>> staged=hasStageTransactions
            ? jdbc.query("select outbound_id,picking_item_id,quantity_unit,action,quantity from stage_transactions where load_id=:id order by id",Map.of("id",id),(r,n)->Map.of("outbound",r.getLong(1),"item",r.getLong(2),"unit",r.getString(3),"action",r.getString(4),"quantity",r.getBigDecimal(5)))
            : List.of();
        BigDecimal net=staged.stream().map(x->"STAGE".equals(x.get("action"))?(BigDecimal)x.get("quantity"):((BigDecimal)x.get("quantity")).negate()).reduce(BigDecimal.ZERO,BigDecimal::add);
        String current=fingerprint(id,staged);List<String> savedRows=hasVerificationTransactions
            ? jdbc.query("select manifest_fingerprint from load_verification_transactions where load_id=:id and transaction_type='COMPLETE' order by id desc limit 1",Map.of("id",id),(r,n)->r.getString(1))
            : List.of();
        String saved=savedRows.isEmpty()?null:savedRows.get(0);
        Map<String,Object>x=new LinkedHashMap<>();x.put("load_id",id);x.put("staged_quantity",net.toPlainString());x.put("verification_complete",!savedRows.isEmpty());x.put("saved_manifest_fingerprint",saved);x.put("current_manifest_fingerprint",current);x.put("manifest_matches",saved!=null&&saved.equals(current));return x;
    }

    private boolean tableExists(String tableName) {
        Boolean exists=jdbc.queryForObject("select to_regclass(:table_name) is not null",Map.of("table_name",tableName),Boolean.class);
        return Boolean.TRUE.equals(exists);
    }

    private String fingerprint(long id,List<Map<String,Object>> rows) {
        List<Long> members=jdbc.query("select id from outbound_orders where load_id=:id order by id",Map.of("id",id),(r,n)->r.getLong(1));TreeMap<StageKey,BigDecimal> totals=new TreeMap<>();
        for(var x:rows){StageKey k=new StageKey((Long)x.get("outbound"),(Long)x.get("item"),(String)x.get("unit"));BigDecimal q=(BigDecimal)x.get("quantity");totals.merge(k,"STAGE".equals(x.get("action"))?q:q.negate(),BigDecimal::add);}
        List<String> parts=new ArrayList<>();totals.forEach((k,v)->{if(v.signum()!=0)parts.add(k+":"+v);});String canonical="members:"+members.stream().map(String::valueOf).reduce((a,b)->a+","+b).orElse("")+"|staged:"+String.join(";",parts);
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}
    }

    private Map<String,Object> loadRow(ResultSet r)throws SQLException {Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));x.put("load_no",r.getString("load_no"));x.put("warehouse_id",r.getLong("warehouse_id"));Long carrier=nlong(r,"carrier_id");x.put("carrier_id",carrier);x.put("status",r.getString("status"));for(String k:List.of("appointment_reference","destination_name","destination_address","driver_name","driver_phone","tractor_no","trailer_no","seal_no","notes"))x.put(k,r.getString(k));x.put("appointment_time",time(r,"appointment_time"));x.put("created_at",time(r,"created_at"));x.put("updated_at",time(r,"updated_at"));x.put("warehouse",ref(r.getLong("warehouse_id"),r.getString("warehouse_code"),r.getString("warehouse_name")));x.put("carrier",carrier==null?null:ref(carrier,r.getString("carrier_code"),r.getString("carrier_name")));return x;}
    private Map<String,Object> outbound(ResultSet r)throws SQLException {Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));x.put("ob_no",r.getString("ob_no"));x.put("fba_reference",r.getString("fba_no"));x.put("destination",r.getString("fc_code"));for(String k:List.of("pallet_qty","carton_qty","weight_lbs","cbm"))x.put(k,r.getBigDecimal(k).toPlainString());x.put("status",List.of("NEW","HOLD","IN_PROGRESS","CONFIRMED","DISPATCHED","COMPLETED","CANCELED","EXCEPTION").get(r.getInt("status")));return x;}
    private Map<String,Object> workOrder(ResultSet r)throws SQLException {Map<String,Object>x=new LinkedHashMap<>();for(String k:List.of("id","assigned_to"))x.put(k,nlong(r,k));for(String k:List.of("work_order_no","work_order_type","status","priority","assigned_team","assignee_name"))x.put(k,r.getString(k));for(String k:List.of("created_at","started_at","completed_at"))x.put(k,time(r,k));return x;}
    private Map<String,Object> exception(ResultSet r)throws SQLException {Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));for(String k:List.of("exception_no","severity","status","title"))x.put(k,r.getString(k));return x;}
    private Map<String,Object> meta(int p,int s,int t){Map<String,Object>x=new LinkedHashMap<>();x.put("page",p);x.put("per_page",s);x.put("total",t);x.put("total_pages",(t+s-1)/s);return x;}
    private String sum(List<Map<String,Object>> rows,String k){return rows.stream().map(x->new BigDecimal((String)x.get(k))).reduce(BigDecimal.ZERO,BigDecimal::add).toPlainString();}
    private void scope(UserAccount u,MapSqlParameterSource p,List<String>f,String col){if(!"ADMIN".equals(u.role())&&"SELECTED".equals(u.warehouseScopeMode())){if(u.warehouseIds().isEmpty())f.add("false");else{p.addValue("scope_w",u.warehouseIds());f.add(col+" in (:scope_w)");}}}
    private void exact(List<String>f,MapSqlParameterSource p,String k,Object v,String col){if(v!=null){p.addValue(k,v);f.add(col+"=:"+k);}}private String where(List<String>f){return f.isEmpty()?"":" where "+String.join(" and ",f);}private Long nlong(ResultSet r,String k)throws SQLException{long v=r.getLong(k);return r.wasNull()?null:v;}private Object time(ResultSet r,String k)throws SQLException{Timestamp t=r.getTimestamp(k);return t==null?null:t.toInstant().atOffset(ZoneOffset.UTC);}private Map<String,Object>ref(long id,String code,String name){Map<String,Object>x=new LinkedHashMap<>();x.put("id",id);x.put("code",code);x.put("name",name);return x;}
    private record StageKey(long outboundId,long itemId,String unit) implements Comparable<StageKey>{public int compareTo(StageKey o){int c=Long.compare(outboundId,o.outboundId);if(c==0)c=Long.compare(itemId,o.itemId);return c==0?unit.compareTo(o.unit):c;}public String toString(){return outboundId+":"+itemId+":"+unit;}}
}

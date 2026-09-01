package com.dlxyuki.wms.operationalexception;

import com.dlxyuki.wms.user.UserAccount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class OperationalExceptionRepository {
    private final NamedParameterJdbcTemplate jdbc;
    OperationalExceptionRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc=jdbc; }

    Object list(int page,int size,String q,String status,String severity,String type,Long warehouseId,Long assignedTo,OffsetDateTime from,OffsetDateTime to,UserAccount user) {
        MapSqlParameterSource p=new MapSqlParameterSource();List<String> base=new ArrayList<>();scope(user,p,base);
        if(q!=null&&!q.isBlank()){p.addValue("q","%"+q.trim()+"%");base.add("(oe.exception_no ilike :q or oe.title ilike :q or oe.description ilike :q)");}
        exact(base,p,"severity",severity,"oe.severity::text");exact(base,p,"type",type,"oe.exception_type::text");
        if(warehouseId!=null)exact(base,p,"warehouse",warehouseId,"oe.warehouse_id");if(assignedTo!=null)exact(base,p,"assigned",assignedTo,"oe.assigned_to");
        if(from!=null){p.addValue("reported_from",from.toInstant());base.add("oe.reported_at>=:reported_from");}if(to!=null){p.addValue("reported_to",to.toInstant());base.add("oe.reported_at<=:reported_to");}
        Map<String,Object> counts=new LinkedHashMap<>();for(String s:List.of("OPEN","INVESTIGATING","RESOLVED","CANCELED"))counts.put(s,0);
        jdbc.query("select oe.status::text status,count(*) n from operational_exceptions oe"+where(base)+" group by oe.status",p,r->{counts.put(r.getString("status"),r.getInt("n"));});
        List<String> filters=new ArrayList<>(base);exact(filters,p,"status",status,"oe.status::text");
        Integer total=jdbc.queryForObject("select count(*) from operational_exceptions oe"+where(filters),p,Integer.class);
        p.addValue("limit",size).addValue("offset",(page-1)*size);
        List<Map<String,Object>> data=jdbc.query("select oe.id from operational_exceptions oe"+where(filters)+" order by oe.reported_at desc,oe.id desc limit :limit offset :offset",p,(r,n)->read(r.getLong(1)));
        Map<String,Object>x=new LinkedHashMap<>();x.put("data",data);x.put("meta",meta(page,size,total==null?0:total));x.put("counts",counts);return x;
    }

    Optional<Map<String,Object>> find(long id,UserAccount user) {
        MapSqlParameterSource p=new MapSqlParameterSource("id",id);List<String>f=new ArrayList<>(List.of("oe.id=:id"));scope(user,p,f);
        return jdbc.query("select oe.id from operational_exceptions oe"+where(f),p,(r,n)->read(r.getLong(1))).stream().findFirst();
    }

    Map<String,Object> events(long id,String order,int limit,int offset) {
        MapSqlParameterSource p=new MapSqlParameterSource().addValue("id",id).addValue("limit",limit).addValue("offset",offset);
        Integer total=jdbc.queryForObject("select count(*) from operational_exception_events where operational_exception_id=:id",p,Integer.class);String d="asc".equals(order)?"asc":"desc";
        List<Map<String,Object>> data=jdbc.query("select e.*,u.display_name actor_name from operational_exception_events e left join users u on u.id=e.actor_user_id where e.operational_exception_id=:id order by e.created_at "+d+",e.id "+d+" limit :limit offset :offset",p,(r,n)->event(r));
        Map<String,Object>x=new LinkedHashMap<>();x.put("data",data);x.put("total",total==null?0:total);x.put("limit",limit);x.put("offset",offset);return x;
    }

    private Map<String,Object> read(long id) {
        String sql="""
            select oe.*,u.display_name assignee_name,
              ob.ob_no outbound_label,l.load_no load_label,ct.container_number container_label,
              pl.picking_no picking_label,b.bol_no bol_label
            from operational_exceptions oe left join users u on u.id=oe.assigned_to
            left join outbound_orders ob on ob.id=oe.outbound_id left join loads l on l.id=oe.load_id
            left join container_trackings ct on ct.id=oe.container_tracking_id left join picking_lists pl on pl.id=oe.picking_list_id
            left join bols b on b.id=oe.bol_id where oe.id=:id
            """;
        Map<String,Object>x=jdbc.queryForObject(sql,Map.of("id",id),(r,n)->exception(r));
        x.put("work_orders",jdbc.query("select id,work_order_no,status::text status,priority::text priority from work_orders where operational_exception_id=:id order by id",Map.of("id",id),(r,n)->{
            Map<String,Object>w=new LinkedHashMap<>();w.put("id",r.getLong("id"));w.put("work_order_no",r.getString("work_order_no"));w.put("status",r.getString("status"));w.put("priority",r.getString("priority"));return w;}));return x;
    }
    private Map<String,Object> exception(ResultSet r)throws SQLException {
        Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));
        for(String k:List.of("exception_no","exception_type","severity","status","title","description"))x.put(k,r.getString(k));x.put("warehouse_id",r.getLong("warehouse_id"));
        Map<String,Object> related=new LinkedHashMap<>();related(r,x,related,"outbound_id","outbound","outbound_label");related(r,x,related,"load_id","load","load_label");related(r,x,related,"container_tracking_id","container","container_label");related(r,x,related,"picking_list_id","picking","picking_label");related(r,x,related,"bol_id","bol","bol_label");
        x.put("assigned_to",nlong(r,"assigned_to"));x.put("assigned_team",r.getString("assigned_team"));x.put("assignee_name",r.getString("assignee_name"));x.put("reported_at",time(r,"reported_at"));x.put("reported_by",r.getLong("reported_by"));x.put("resolved_at",time(r,"resolved_at"));x.put("resolved_by",nlong(r,"resolved_by"));x.put("resolution",r.getString("resolution"));x.put("created_at",time(r,"created_at"));x.put("updated_at",time(r,"updated_at"));x.put("related",related);return x;
    }
    private void related(ResultSet r,Map<String,Object>x,Map<String,Object>related,String idCol,String key,String labelCol)throws SQLException{Long id=nlong(r,idCol);x.put(idCol,id);if(id!=null){Map<String,Object>v=new LinkedHashMap<>();v.put("id",id);v.put("label",r.getString(labelCol));related.put(key,v);}}
    private Map<String,Object> event(ResultSet r)throws SQLException{Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));x.put("event_type",r.getString("event_type"));Long actor=nlong(r,"actor_user_id");x.put("actor_user_id",actor);String name=r.getString("actor_name");x.put("actor_name",actor==null?"System":name);for(String k:List.of("field_name","old_value","new_value","message"))x.put(k,r.getString(k));x.put("created_at",time(r,"created_at"));return x;}
    private void scope(UserAccount u,MapSqlParameterSource p,List<String>f){if(!"ADMIN".equals(u.role())&&"SELECTED".equals(u.warehouseScopeMode())){if(u.warehouseIds().isEmpty())f.add("false");else{p.addValue("scope_w",u.warehouseIds());f.add("oe.warehouse_id in (:scope_w)");}}}
    private void exact(List<String>f,MapSqlParameterSource p,String key,Object value,String column){if(value!=null){p.addValue(key,value);f.add(column+"=:"+key);}}
    private String where(List<String>f){return f.isEmpty()?"":" where "+String.join(" and ",f);}
    private Map<String,Object> meta(int page,int size,int total){Map<String,Object>x=new LinkedHashMap<>();x.put("page",page);x.put("per_page",size);x.put("total",total);x.put("total_pages",(total+size-1)/size);return x;}
    private Long nlong(ResultSet r,String k)throws SQLException{long v=r.getLong(k);return r.wasNull()?null:v;}
    private Object time(ResultSet r,String k)throws SQLException{Timestamp t=r.getTimestamp(k);return t==null?null:t.toInstant().atOffset(ZoneOffset.UTC);}
}

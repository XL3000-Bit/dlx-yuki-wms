package com.dlxyuki.wms.workorder;

import com.dlxyuki.wms.user.UserAccount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
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
class WorkOrderRepository {
    private final NamedParameterJdbcTemplate jdbc;
    WorkOrderRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc=jdbc; }

    Object list(int page,int size,String q,String status,String type,Long warehouseId,String priority,Long assignedTo,UserAccount user) {
        MapSqlParameterSource p=new MapSqlParameterSource(); List<String> f=new ArrayList<>(); scope(user,p,f);
        if(q!=null&&!q.isEmpty()){p.addValue("q","%"+q.trim()+"%");f.add("wo.work_order_no ilike :q");}
        exact(f,p,"status",status,"wo.status::text"); exact(f,p,"type",type,"wo.work_order_type::text");
        if(warehouseId!=null&&warehouseId!=0)exact(f,p,"warehouse",warehouseId,"wo.warehouse_id");
        exact(f,p,"priority",priority,"wo.priority::text");
        if(assignedTo!=null&&assignedTo!=0)exact(f,p,"assigned",assignedTo,"wo.assigned_to");
        List<Long> ids=jdbc.query("select wo.id from work_orders wo"+where(f)+" order by wo.id desc",p,(r,n)->r.getLong(1));
        int total=ids.size(),start=Math.min((page-1)*size,total),end=Math.min(start+size,total);List<Map<String,Object>> data=new ArrayList<>();
        for(Long id:ids.subList(start,end))data.add(read(id));
        Map<String,Object>x=new LinkedHashMap<>();x.put("data",data);x.put("meta",meta(page,size,total));return x;
    }

    Optional<Map<String,Object>> find(long id,UserAccount user) {
        MapSqlParameterSource p=new MapSqlParameterSource("id",id);List<String>f=new ArrayList<>(List.of("wo.id=:id"));scope(user,p,f);
        return jdbc.query("select wo.id from work_orders wo"+where(f),p,(r,n)->read(r.getLong(1))).stream().findFirst();
    }

    Map<String,Object> events(long id,String order,int limit,int offset) {
        Map<String,Object> p=Map.of("id",id,"limit",limit,"offset",offset);
        Integer total=jdbc.queryForObject("select count(*) from work_order_events where work_order_id=:id",p,Integer.class);
        String direction="asc".equals(order)?"asc":"desc";
        List<Map<String,Object>> data=jdbc.query("""
            select e.*,u.username actor_username,u.display_name actor_display_name from work_order_events e
            left join users u on u.id=e.actor_user_id where e.work_order_id=:id
            order by e.created_at %s,e.id %s limit :limit offset :offset
            """.formatted(direction,direction),p,(r,n)->event(r));
        Map<String,Object>x=new LinkedHashMap<>();x.put("data",data);x.put("total",total==null?0:total);x.put("limit",limit);x.put("offset",offset);return x;
    }

    private Map<String,Object> read(long id) {
        return jdbc.queryForObject("select wo.*,u.display_name assignee_name from work_orders wo left join users u on u.id=wo.assigned_to where wo.id=:id",Map.of("id",id),(r,n)->workOrder(r));
    }
    private Map<String,Object> workOrder(ResultSet r)throws SQLException {
        Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));x.put("work_order_no",r.getString("work_order_no"));x.put("work_order_type",r.getString("work_order_type"));x.put("status",r.getString("status"));x.put("warehouse_id",r.getLong("warehouse_id"));
        for(String k:List.of("load_id","outbound_id","picking_list_id","container_tracking_id","operational_exception_id"))x.put(k,nlong(r,k));
        x.put("priority",r.getString("priority"));x.put("assigned_to",nlong(r,"assigned_to"));x.put("assigned_team",r.getString("assigned_team"));
        for(String k:List.of("scheduled_at","started_at","completed_at"))x.put(k,time(r,k));x.put("notes",r.getString("notes"));x.put("created_by",r.getLong("created_by"));x.put("created_at",time(r,"created_at"));x.put("updated_at",time(r,"updated_at"));x.put("assignee_name",r.getString("assignee_name"));return x;
    }
    private Map<String,Object> event(ResultSet r)throws SQLException {
        Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));
        for(String k:List.of("event_type","field_name","old_value","new_value","message","from_status","to_status"))x.put(k,r.getString(k));
        Long actorId=nlong(r,"actor_user_id");x.put("actor_user_id",actorId);String display=r.getString("actor_display_name");x.put("actor_name",actorId==null?"System":display);
        if(actorId==null)x.put("actor",null);else{Map<String,Object>a=new LinkedHashMap<>();a.put("id",actorId);a.put("username",r.getString("actor_username"));a.put("display_name",display);x.put("actor",a);}
        x.put("assigned_to_before",nlong(r,"assigned_to_before"));x.put("assigned_to_after",nlong(r,"assigned_to_after"));
        for(String k:List.of("assigned_team_before","assigned_team_after","priority_before","priority_after","note"))x.put(k,r.getString(k));x.put("created_at",time(r,"created_at"));return x;
    }
    private Map<String,Object> meta(int page,int size,int total){Map<String,Object>x=new LinkedHashMap<>();x.put("page",page);x.put("per_page",size);x.put("total",total);x.put("total_pages",(total+size-1)/size);return x;}
    private void scope(UserAccount u,MapSqlParameterSource p,List<String>f){if(!"ADMIN".equals(u.role())&&"SELECTED".equals(u.warehouseScopeMode())){if(u.warehouseIds().isEmpty())f.add("false");else{p.addValue("scope_w",u.warehouseIds());f.add("wo.warehouse_id in (:scope_w)");}}}
    private void exact(List<String>f,MapSqlParameterSource p,String key,Object value,String column){if(value!=null){p.addValue(key,value);f.add(column+"=:"+key);}}
    private String where(List<String>f){return f.isEmpty()?"":" where "+String.join(" and ",f);}
    private Long nlong(ResultSet r,String k)throws SQLException{long v=r.getLong(k);return r.wasNull()?null:v;}
    private Object time(ResultSet r,String k)throws SQLException{Timestamp t=r.getTimestamp(k);return t==null?null:t.toInstant().atOffset(ZoneOffset.UTC);}
}

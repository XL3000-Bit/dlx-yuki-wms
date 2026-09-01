package com.dlxyuki.wms.pickingbol;

import com.dlxyuki.wms.user.UserAccount;
import java.math.BigDecimal;
import java.sql.*;
import java.time.ZoneOffset;
import java.util.*;
import org.springframework.jdbc.core.namedparam.*;
import org.springframework.stereotype.Repository;

@Repository
class PickingBolRepository {
    private final NamedParameterJdbcTemplate jdbc;
    PickingBolRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }
    List<Map<String,Object>> listPicking(UserAccount user) { return query(null,user); }
    Optional<Map<String,Object>> findPicking(long id,UserAccount user) { return query(id,user).stream().findFirst(); }
    private List<Map<String,Object>> query(Long id,UserAccount user){
        MapSqlParameterSource p=new MapSqlParameterSource();List<String> f=new ArrayList<>();if(id!=null){p.addValue("id",id);f.add("p.id=:id");}scope(user,p,f);
        return jdbc.query("""
          select p.id,p.picking_no,p.outbound_order_id,p.status,p.assigned_team,p.created_at,p.completed_at,
          coalesce(sum(i.planned_pallet_qty),0) planned_pallet_qty,coalesce(sum(i.planned_carton_qty),0) planned_carton_qty,
          coalesce(sum(i.picked_pallet_qty),0) picked_pallet_qty,coalesce(sum(i.picked_carton_qty),0) picked_carton_qty
          from picking_lists p join outbound_orders o on o.id=p.outbound_order_id left join picking_list_items i on i.picking_list_id=p.id
          """+where(f)+" group by p.id order by p.id desc limit 200",p,(r,n)->picking(r));
    }
    List<Map<String,Object>> pickingItems(long id){return jdbc.query("""
      select i.sequence_no,l.location_code,i.container_number,i.fc_code,i.marking,i.planned_pallet_qty,
      i.planned_carton_qty,i.planned_weight_lbs,i.planned_cbm from picking_list_items i
      left join warehouse_locations l on l.id=i.location_id where i.picking_list_id=:id order by i.sequence_no,i.id
      """,Map.of("id",id),(r,n)->item(r));}
    List<Map<String,Object>> listBols(UserAccount user){return queryBols(null,user);}
    Optional<Map<String,Object>> findBol(long id,UserAccount user){return queryBols(id,user).stream().findFirst();}
    private List<Map<String,Object>> queryBols(Long id,UserAccount user){
        MapSqlParameterSource p=new MapSqlParameterSource();List<String> f=new ArrayList<>();if(id!=null){p.addValue("id",id);f.add("b.id=:id");}scope(user,p,f);
        return jdbc.query("""
          select b.id,b.bol_no,b.outbound_order_id,b.fba_shipment_id,b.ship_from_name,b.ship_from_address,
          b.ship_to_name,b.ship_to_address,b.amazon_fc_code,b.status,b.created_at,
          coalesce(sum(i.pallet_qty),0) total_pallet_qty,coalesce(sum(i.carton_qty),0) total_carton_qty,
          coalesce(sum(i.weight_lbs),0) total_weight_lbs,coalesce(sum(i.cbm),0) total_cbm
          from bols b join outbound_orders o on o.id=b.outbound_order_id left join bol_items i on i.bol_id=b.id
          """+where(f)+" group by b.id order by b.id desc limit 200",p,(r,n)->bol(r));
    }
    List<Map<String,Object>> bolItems(long id){return jdbc.query("""
      select o.ob_no,b.ship_from_address,b.ship_to_address,b.amazon_fc_code,i.container_number,i.pallet_qty,
      i.carton_qty,i.weight_lbs,i.cbm from bols b join outbound_orders o on o.id=b.outbound_order_id
      join bol_items i on i.bol_id=b.id where b.id=:id order by i.id
      """,Map.of("id",id),(r,n)->{Map<String,Object>x=new LinkedHashMap<>();for(String k:List.of("ob_no","ship_from_address","ship_to_address","amazon_fc_code","container_number"))x.put(k,r.getString(k));for(String k:List.of("pallet_qty","carton_qty","weight_lbs","cbm"))x.put(k,decimal(r,k));return x;});}
    private Map<String,Object> picking(ResultSet r)throws SQLException{Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));x.put("picking_no",r.getString("picking_no"));x.put("outbound_order_id",r.getLong("outbound_order_id"));int s=r.getInt("status");x.put("status",s);x.put("status_name",List.of("New","Printed","In Progress","Completed","Canceled","Exception").get(s));x.put("assigned_team",r.getString("assigned_team"));for(String k:List.of("planned_pallet_qty","planned_carton_qty","picked_pallet_qty","picked_carton_qty"))x.put(k,decimal(r,k));x.put("created_at",time(r,"created_at"));x.put("completed_at",time(r,"completed_at"));return x;}
    private Map<String,Object> item(ResultSet r)throws SQLException{Map<String,Object>x=new LinkedHashMap<>();x.put("sequence_no",r.getInt("sequence_no"));for(String k:List.of("location_code","container_number","fc_code","marking"))x.put(k,r.getString(k));for(String k:List.of("planned_pallet_qty","planned_carton_qty","planned_weight_lbs","planned_cbm"))x.put(k,decimal(r,k));return x;}
    private Map<String,Object> bol(ResultSet r)throws SQLException{Map<String,Object>x=new LinkedHashMap<>();x.put("id",r.getLong("id"));x.put("bol_no",r.getString("bol_no"));x.put("outbound_order_id",r.getLong("outbound_order_id"));long f=r.getLong("fba_shipment_id");x.put("fba_shipment_id",r.wasNull()?null:f);for(String k:List.of("ship_from_name","ship_from_address","ship_to_name","ship_to_address","amazon_fc_code"))x.put(k,r.getString(k));int s=r.getInt("status");x.put("status",s);x.put("status_name",List.of("Draft","Generated","Printed","Completed","Canceled").get(s));for(String k:List.of("total_pallet_qty","total_carton_qty","total_weight_lbs","total_cbm"))x.put(k,decimal(r,k));x.put("fc_address_missing",r.getString("amazon_fc_code")!=null&&r.getString("ship_to_address")==null);x.put("created_at",time(r,"created_at"));return x;}
    private void scope(UserAccount u,MapSqlParameterSource p,List<String>f){if("ADMIN".equalsIgnoreCase(u.role()))return;if("SELECTED".equalsIgnoreCase(u.warehouseScopeMode())){if(u.warehouseIds().isEmpty())f.add("false");else{p.addValue("scope_w",u.warehouseIds());f.add("o.warehouse_id in (:scope_w)");}}if("SELECTED".equalsIgnoreCase(u.customerScopeMode())){if(u.customerIds().isEmpty())f.add("false");else{p.addValue("scope_c",u.customerIds());f.add("o.customer_id in (:scope_c)");}}}
    private String where(List<String>f){return f.isEmpty()?"":" where "+String.join(" and ",f);}private String decimal(ResultSet r,String k)throws SQLException{BigDecimal v=r.getBigDecimal(k);return(v==null?BigDecimal.ZERO:v).toPlainString();}private Object time(ResultSet r,String k)throws SQLException{Timestamp t=r.getTimestamp(k);return t==null?null:t.toInstant().atOffset(ZoneOffset.UTC);}
}

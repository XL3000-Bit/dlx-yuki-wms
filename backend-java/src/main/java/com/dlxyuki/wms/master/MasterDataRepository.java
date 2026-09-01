package com.dlxyuki.wms.master;

import com.dlxyuki.wms.user.UserAccount;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.*;
import org.springframework.stereotype.Repository;

@Repository
public class MasterDataRepository {
    private final JdbcTemplate jdbc; private final NamedParameterJdbcTemplate named;
    public MasterDataRepository(JdbcTemplate jdbc){this.jdbc=jdbc;this.named=new NamedParameterJdbcTemplate(jdbc);}
    public List<Map<String,Object>> customers(UserAccount u){return scoped("customers",u.role(),u.customerScopeMode(),u.customerIds(),"id",null);}
    public List<Map<String,Object>> warehouses(UserAccount u){return scoped("warehouses",u.role(),u.warehouseScopeMode(),u.warehouseIds(),"id",null);}
    public List<Map<String,Object>> areas(UserAccount u){return scoped("warehouse_areas",u.role(),u.warehouseScopeMode(),u.warehouseIds(),"warehouse_id",null);}
    public List<Map<String,Object>> locations(UserAccount u,String code){return scoped("warehouse_locations",u.role(),u.warehouseScopeMode(),u.warehouseIds(),"warehouse_id",code);}
    public List<Map<String,Object>> carriers(){return rows("select * from carriers");}
    public List<Map<String,Object>> fcs(){return rows("select * from amazon_fc_addresses");}
    public Optional<Map<String,Object>> fc(String code){return rows("select * from amazon_fc_addresses where fc_code=?",code.toUpperCase(Locale.ROOT)).stream().findFirst();}
    private List<Map<String,Object>> scoped(String table,String role,String mode,List<Long> ids,String column,String code){
        String sql="select * from "+table+" where 1=1";MapSqlParameterSource p=new MapSqlParameterSource();
        if(!"ADMIN".equals(role) && "SELECTED".equals(mode)){if(ids.isEmpty())return List.of();sql+=" and "+column+" in (:ids)";p.addValue("ids",ids);}
        if(code!=null&&!code.isBlank()){sql+=" and location_code ilike :code";p.addValue("code","%"+code+"%");}
        return normalize(named.queryForList(sql,p));
    }
    public Map<String,Object> create(String kind,Map<String,Object> body){Spec s=spec(kind);LinkedHashMap<String,Object> values=new LinkedHashMap<>();for(String c:s.columns())if(body.containsKey(c))values.put(c,body.get(c));for(String req:s.required())if(!values.containsKey(req)||values.get(req)==null||values.get(req).toString().isBlank())throw new IllegalArgumentException(req);if(kind.equals("amazon-fc-addresses"))values.put("fc_code",values.get("fc_code").toString().toUpperCase(Locale.ROOT));String cols=String.join(",",values.keySet()),params=String.join(",",values.keySet().stream().map(x->":"+x).toList());return normalize(named.queryForMap("insert into "+s.table()+" ("+cols+") values ("+params+") returning *",values));}
    private Spec spec(String k){return switch(k){
        case "customers"->new Spec("customers",List.of("customer_code","customer_name","contact_name","phone","email","remark"),List.of("customer_code","customer_name"));
        case "warehouses"->new Spec("warehouses",List.of("warehouse_code","warehouse_name","address","city","state","zip_code","country"),List.of("warehouse_code","warehouse_name","address","city","state","zip_code"));
        case "warehouse-areas"->new Spec("warehouse_areas",List.of("warehouse_id","area_code","area_name"),List.of("warehouse_id","area_code","area_name"));
        case "warehouse-locations"->new Spec("warehouse_locations",List.of("warehouse_id","area_id","location_code","location_name"),List.of("warehouse_id","area_id","location_code","location_name"));
        case "carriers"->new Spec("carriers",List.of("carrier_code","carrier_name","scac","contact_name","phone","email","remark"),List.of("carrier_code","carrier_name"));
        case "amazon-fc-addresses"->new Spec("amazon_fc_addresses",List.of("fc_code","fc_name","address_line1","address_line2","city","state","zip_code","country"),List.of("fc_code","address_line1","city","state","zip_code"));
        default->throw new IllegalArgumentException("Unknown master type");};}
    private List<Map<String,Object>> rows(String sql,Object...args){return normalize(jdbc.queryForList(sql,args));}
    private List<Map<String,Object>> normalize(List<Map<String,Object>> rows){return rows.stream().map(this::normalize).toList();}
    private Map<String,Object> normalize(Map<String,Object> row){Map<String,Object> out=new LinkedHashMap<>();row.forEach((k,v)->out.put(k.toLowerCase(Locale.ROOT),v));return out;}
    private record Spec(String table,List<String> columns,List<String> required){}
}

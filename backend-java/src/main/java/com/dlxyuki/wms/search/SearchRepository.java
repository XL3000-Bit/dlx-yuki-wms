package com.dlxyuki.wms.search;

import com.dlxyuki.wms.user.UserAccount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SearchRepository {
    public static final List<String> TYPES = List.of("CONTAINER","OUTBOUND","FBA","PICKING","BOL","LOAD","WORK_ORDER","EXCEPTION","DOCUMENT");
    private final NamedParameterJdbcTemplate jdbc;
    public SearchRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }

    record Candidate(String type,long id,String primary,String secondary,String status,String warehouse,
                     String customer,String route,int rank,int groupOrder) {}

    List<Candidate> search(String query, int cap, UserAccount user) {
        var out = new ArrayList<Candidate>();
        out.addAll(run("CONTAINER",0,cap,query,user,
            "container_trackings x left join warehouses w on w.id=x.warehouse_id",
            List.of("x.container_number","x.mbl_number","x.hbl_number","x.filing_number","x.customer_reference"),
            "x.container_number","x.mbl_number","x.tracking_status::text","coalesce(w.warehouse_code,x.delivery_warehouse_raw)","null",
            "'/container-tracking?selected='||x.id", "x.warehouse_id", null));
        out.addAll(run("OUTBOUND",1,cap,query,user,
            "outbound_orders x left join warehouses w on w.id=x.warehouse_id left join customers c on c.id=x.customer_id",
            List.of("x.ob_no","x.reference_no","x.appointment_reference","x.picking_reference","x.bol_reference","x.pod_reference"),
            "x.ob_no","x.reference_no",obStatus("x.status"),"w.warehouse_code","c.customer_name",
            "'/outbound/dispatch?selected_ob='||x.id", "x.warehouse_id", "x.customer_id"));
        out.addAll(run("FBA",2,cap,query,user,
            "fba_shipments x left join warehouses w on w.id=x.warehouse_id left join customers c on c.id=x.customer_id",
            List.of("x.fba_no","x.reference_no","x.shipment_id","x.st_number","x.po_number","x.source_reference"),
            "x.fba_no","x.st_number",fbaStatus("x.status"),"w.warehouse_code","c.customer_name",
            "'/fba?selected='||x.id", "x.warehouse_id", "x.customer_id"));
        out.addAll(run("PICKING",3,cap,query,user,
            "picking_lists x join outbound_orders o on o.id=x.outbound_order_id left join warehouses w on w.id=o.warehouse_id left join customers c on c.id=o.customer_id",
            List.of("x.picking_no"),"x.picking_no","o.ob_no",pickingStatus("x.status"),"w.warehouse_code","c.customer_name",
            "'/outbound/picking'", "o.warehouse_id", "o.customer_id"));
        out.addAll(run("BOL",4,cap,query,user,
            "bols x join outbound_orders o on o.id=x.outbound_order_id left join warehouses w on w.id=x.warehouse_id left join customers c on c.id=x.customer_id",
            List.of("x.bol_no"),"x.bol_no","o.ob_no",bolStatus("x.status"),"w.warehouse_code","c.customer_name",
            "'/outbound/bol'", "x.warehouse_id", "x.customer_id"));
        out.addAll(run("LOAD",5,cap,query,user,
            "loads x left join warehouses w on w.id=x.warehouse_id",List.of("x.load_no"),"x.load_no",
            "(select count(*)::text||' outbounds' from outbound_orders o where o.load_id=x.id)","x.status::text","w.warehouse_code","null",
            "'/loads?selected='||x.id", "x.warehouse_id", null));
        out.addAll(run("WORK_ORDER",6,cap,query,user,
            "work_orders x left join warehouses w on w.id=x.warehouse_id",List.of("x.work_order_no"),"x.work_order_no","x.work_order_type::text",
            "x.status::text","w.warehouse_code","null","'/work-orders?selected='||x.id", "x.warehouse_id", null));
        out.addAll(run("EXCEPTION",7,cap,query,user,
            "operational_exceptions x left join warehouses w on w.id=x.warehouse_id",List.of("x.exception_no"),"x.exception_no","x.title",
            "x.status::text","w.warehouse_code","null","'/trouble-shoot?selected='||x.id", "x.warehouse_id", null));
        out.addAll(run("DOCUMENT",8,cap,query,user,
            "operational_documents x left join warehouses w on w.id=x.warehouse_id left join customers c on c.id=x.customer_id",
            List.of("x.document_no","x.original_filename","x.title"),"x.document_no","x.original_filename","x.status::text","w.warehouse_code","c.customer_name",
            "'/documents?selected='||x.id", "x.warehouse_id", "x.customer_id"));
        return out;
    }

    private List<Candidate> run(String type,int order,int cap,String query,UserAccount user,String from,List<String> fields,
        String primary,String secondary,String status,String warehouse,String customer,String route,String warehouseId,String customerId) {
        String match = fields.stream().map(f -> "lower(coalesce("+f+",'')) like :contains").reduce((a,b)->a+" or "+b).orElse("false");
        String exact = fields.stream().map(f -> "lower(coalesce("+f+",''))=:exact").reduce((a,b)->a+" or "+b).orElse("false");
        String prefix = fields.stream().map(f -> "lower(coalesce("+f+",'')) like :prefix").reduce((a,b)->a+" or "+b).orElse("false");
        StringBuilder scope = new StringBuilder(); var p = new MapSqlParameterSource()
            .addValue("exact",query.toLowerCase()).addValue("prefix",query.toLowerCase()+"%")
            .addValue("contains","%"+query.toLowerCase()+"%").addValue("cap",cap);
        if (!"ADMIN".equals(user.role()) && "SELECTED".equals(user.warehouseScopeMode())) {
            scope.append(" and ").append(warehouseId).append(" in (:warehouseIds)"); p.addValue("warehouseIds", safeIds(user.warehouseIds()));
        }
        if (customerId != null && !"ADMIN".equals(user.role()) && "SELECTED".equals(user.customerScopeMode())) {
            scope.append(" and ").append(customerId).append(" in (:customerIds)"); p.addValue("customerIds", safeIds(user.customerIds()));
        }
        String sql="select x.id,"+primary+" primary_ref,"+secondary+" secondary_ref,"+status+" status_name,"+warehouse+" warehouse_name,"+customer+" customer_name,"+route+" target_route,case when ("+exact+") then 1 when ("+prefix+") then 2 else 3 end match_rank from "+from+" where ("+match+")"+scope+" limit :cap";
        return jdbc.query(sql,p,(r,n)->candidate(type,order,r));
    }
    private static List<Long> safeIds(List<Long> ids) { return ids == null || ids.isEmpty() ? List.of(-1L) : ids; }
    private static Candidate candidate(String type,int order,ResultSet r)throws SQLException { return new Candidate(type,r.getLong("id"),r.getString("primary_ref"),r.getString("secondary_ref"),r.getString("status_name"),r.getString("warehouse_name"),r.getString("customer_name"),r.getString("target_route"),r.getInt("match_rank"),order); }
    private static String obStatus(String c){return "case "+c+" when 0 then 'NEW' when 1 then 'HOLD' when 2 then 'IN_PROGRESS' when 3 then 'CONFIRMED' when 4 then 'DISPATCHED' when 5 then 'COMPLETED' when 6 then 'CANCELED' when 7 then 'EXCEPTION' else "+c+"::text end";}
    private static String fbaStatus(String c){return "case "+c+" when 0 then 'DRAFT' when 1 then 'PLANNING' when 2 then 'ALLOCATED' when 3 then 'READY' when 4 then 'SCHEDULED' when 5 then 'IN_TRANSIT' when 6 then 'DELIVERED' when 7 then 'COMPLETED' when 8 then 'HOLD' when 9 then 'CANCELED' else "+c+"::text end";}
    private static String pickingStatus(String c){return "case "+c+" when 0 then 'NEW' when 1 then 'PRINTED' when 2 then 'IN_PROGRESS' when 3 then 'COMPLETED' when 4 then 'CANCELED' when 5 then 'EXCEPTION' else "+c+"::text end";}
    private static String bolStatus(String c){return "case "+c+" when 0 then 'DRAFT' when 1 then 'GENERATED' when 2 then 'PRINTED' when 3 then 'COMPLETED' when 4 then 'CANCELED' else "+c+"::text end";}
}

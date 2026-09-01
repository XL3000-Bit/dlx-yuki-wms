package com.dlxyuki.wms.inbound;

import com.dlxyuki.wms.user.UserAccount;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.jdbc.core.namedparam.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InboundRepository {
    private static final Set<String> SORTABLE = Set.of("id", "inbound_no", "container_number", "unload_date", "received_date", "fc_code", "pallet_qty", "created_at");
    private static final String SELECT = """
        select i.*, c.customer_code, c.customer_name, w.warehouse_code, w.warehouse_name,
               l.location_code, l.location_name, u.display_name creator_display_name,
               il.id inventory_lot_id
          from inbound_records i
          left join customers c on c.id=i.customer_id
          left join warehouses w on w.id=i.warehouse_id
          left join warehouse_locations l on l.id=i.location_id
          left join users u on u.id=i.created_by
          left join inventory_lots il on il.source_inbound_id=i.id
        """;
    private final NamedParameterJdbcTemplate jdbc;
    public InboundRepository(JdbcTemplate jdbc) { this.jdbc = new NamedParameterJdbcTemplate(jdbc); }

    public InboundListResponse list(InboundQuery q, UserAccount user) {
        MapSqlParameterSource p = new MapSqlParameterSource();
        String where = filters(q, user, p);
        long total = Optional.ofNullable(jdbc.queryForObject("select count(*) from inbound_records i " + where, p, Long.class)).orElse(0L);
        String sort = SORTABLE.contains(q.sortBy()) ? q.sortBy() : "id";
        String order = "asc".equals(q.sortOrder()) ? "asc" : "desc";
        p.addValue("limit", q.perPage()).addValue("offset", (q.page() - 1) * q.perPage());
        List<InboundResponse> rows = jdbc.query(SELECT + where + " order by i." + sort + " " + order + " limit :limit offset :offset", p, this::map);
        long pages = total == 0 ? 0 : (total + q.perPage() - 1) / q.perPage();
        return new InboundListResponse(rows, new InboundListResponse.PaginationMeta(q.page(), q.perPage(), total, pages));
    }

    public Optional<InboundResponse> find(long id, UserAccount user) {
        MapSqlParameterSource p = new MapSqlParameterSource("id", id);
        String scope = scope(user, p);
        return jdbc.query(SELECT + " where i.id=:id" + scope, p, this::map).stream().findFirst();
    }

    public long insert(InboundRequest value, long userId, LocalDate today) {
        String prefix = "IB" + String.format("%02d%02d%02d", today.getYear() % 100, today.getMonthValue(), today.getDayOfMonth());
        jdbc.query("select pg_advisory_xact_lock(hashtext(:prefix))", Map.of("prefix", prefix), resultSet -> { });
        String last = jdbc.queryForObject("select max(inbound_no) from inbound_records where inbound_no like :pattern", Map.of("pattern", prefix + "%"), String.class);
        int sequence = last == null ? 1 : Integer.parseInt(last.substring(last.length() - 4)) + 1;
        MapSqlParameterSource p = values(value).addValue("inbound_no", prefix + String.format("%04d", sequence)).addValue("created_by", userId);
        return Objects.requireNonNull(jdbc.queryForObject("""
            insert into inbound_records (inbound_no,container_number,customer_id,warehouse_id,unload_date,received_date,fc_code,marking,pallet_qty,carton_qty,weight_lbs,cbm,location_id,status,remark,created_by)
            values (:inbound_no,:container_number,:customer_id,:warehouse_id,:unload_date,:received_date,:fc_code,:marking,:pallet_qty,:carton_qty,:weight_lbs,:cbm,:location_id,:status,:remark,:created_by) returning id
            """, p, Long.class));
    }

    public void update(long id, InboundRequest value) {
        MapSqlParameterSource p = values(value).addValue("id", id);
        jdbc.update("""
            update inbound_records set container_number=:container_number,customer_id=:customer_id,warehouse_id=:warehouse_id,
            unload_date=:unload_date,received_date=:received_date,fc_code=:fc_code,marking=:marking,pallet_qty=:pallet_qty,
            carton_qty=:carton_qty,weight_lbs=:weight_lbs,cbm=:cbm,location_id=:location_id,status=:status,remark=:remark,
            updated_at=now() where id=:id
            """, p);
    }

    public boolean warehouseExists(long id) { return exists("select exists(select 1 from warehouses where id=:id)", Map.of("id", id)); }
    public boolean customerExists(long id) { return exists("select exists(select 1 from customers where id=:id)", Map.of("id", id)); }
    public boolean locationMatches(long id, long warehouseId) { return exists("select exists(select 1 from warehouse_locations where id=:id and warehouse_id=:warehouse)", Map.of("id", id, "warehouse", warehouseId)); }
    public void audit(long userId, String action, long entityId, String before, String after) {
        jdbc.update("insert into audit_logs(user_id,action,entity_type,entity_id,before_data,after_data) values (:user,'" + action + "','INBOUND',:entity,cast(:before as jsonb),cast(:after as jsonb))",
            new MapSqlParameterSource().addValue("user", userId).addValue("entity", entityId).addValue("before", before).addValue("after", after));
    }

    private boolean exists(String sql, Map<String, ?> p) { return Boolean.TRUE.equals(jdbc.queryForObject(sql, p, Boolean.class)); }
    private MapSqlParameterSource values(InboundRequest v) {
        return new MapSqlParameterSource().addValue("container_number", v.containerNumber()).addValue("customer_id", v.customerId())
            .addValue("warehouse_id", v.warehouseId()).addValue("unload_date", v.unloadDate()).addValue("received_date", v.receivedDate())
            .addValue("fc_code", v.fcCode()).addValue("marking", v.marking()).addValue("pallet_qty", v.effectivePalletQty())
            .addValue("carton_qty", v.effectiveCartonQty()).addValue("weight_lbs", v.weightLbs()).addValue("cbm", v.cbm())
            .addValue("location_id", v.locationId()).addValue("status", v.effectiveStatus()).addValue("remark", v.remark());
    }
    private String filters(InboundQuery q, UserAccount u, MapSqlParameterSource p) {
        List<String> clauses = new ArrayList<>();
        addScope(u, p, clauses);
        if (q.q() != null) { p.addValue("q", "%" + q.q() + "%"); clauses.add("(i.inbound_no ilike :q or i.container_number ilike :q or i.fc_code ilike :q or i.marking ilike :q or i.remark ilike :q)"); }
        if (q.containerNumber() != null) { p.addValue("container_number", "%" + q.containerNumber() + "%"); clauses.add("i.container_number ilike :container_number"); }
        if (q.customerId() != null) { p.addValue("customer_id", q.customerId()); clauses.add("i.customer_id=:customer_id"); }
        if (q.warehouseId() != null) { p.addValue("warehouse_id", q.warehouseId()); clauses.add("i.warehouse_id=:warehouse_id"); }
        if (q.fcCode() != null) { p.addValue("fc_code", "%" + q.fcCode() + "%"); clauses.add("i.fc_code ilike :fc_code"); }
        if (q.locationId() != null) { p.addValue("location_id", q.locationId()); clauses.add("i.location_id=:location_id"); }
        if (q.status() != null) { p.addValue("status", q.status()); clauses.add("i.status=:status"); }
        dateFilter(clauses, p, "unload_from", q.unloadDateFrom(), "i.unload_date>=:unload_from");
        dateFilter(clauses, p, "unload_to", q.unloadDateTo(), "i.unload_date<=:unload_to");
        dateFilter(clauses, p, "received_from", q.receivedDateFrom(), "i.received_date>=:received_from");
        dateFilter(clauses, p, "received_to", q.receivedDateTo(), "i.received_date<=:received_to");
        return clauses.isEmpty() ? "" : " where " + String.join(" and ", clauses);
    }
    private void addScope(UserAccount u, MapSqlParameterSource p, List<String> clauses) {
        if (!"ADMIN".equals(u.role()) && "SELECTED".equals(u.warehouseScopeMode())) { if (u.warehouseIds().isEmpty()) clauses.add("false"); else { p.addValue("scope_warehouses", u.warehouseIds()); clauses.add("i.warehouse_id in (:scope_warehouses)"); } }
        if (!"ADMIN".equals(u.role()) && "SELECTED".equals(u.customerScopeMode())) { if (u.customerIds().isEmpty()) clauses.add("false"); else { p.addValue("scope_customers", u.customerIds()); clauses.add("i.customer_id in (:scope_customers)"); } }
    }
    private String scope(UserAccount u, MapSqlParameterSource p) { List<String> c = new ArrayList<>(); addScope(u, p, c); return c.isEmpty() ? "" : " and " + String.join(" and ", c); }
    private void dateFilter(List<String> c, MapSqlParameterSource p, String key, LocalDate value, String sql) { if (value != null) { p.addValue(key, value); c.add(sql); } }
    private InboundResponse map(ResultSet r, int ignored) throws SQLException {
        LocalDate unload = r.getObject("unload_date", LocalDate.class), received = r.getObject("received_date", LocalDate.class);
        LocalDate base = received != null ? received : unload;
        Integer aging = base == null ? null : (int)Math.max(0, ChronoUnit.DAYS.between(base, LocalDate.now(ZoneId.of("America/Los_Angeles"))));
        Long customerId = nullableLong(r, "customer_id"), warehouseId = nullableLong(r, "warehouse_id");
        Long locationId = nullableLong(r, "location_id"), creatorId = nullableLong(r, "created_by"), lotId = nullableLong(r, "inventory_lot_id");
        return new InboundResponse(r.getLong("id"), r.getString("inbound_no"), r.getString("container_number"),
            customerId == null ? null : new InboundResponse.NamedRef(customerId, r.getString("customer_code"), r.getString("customer_name")),
            warehouseId == null ? null : new InboundResponse.NamedRef(warehouseId, r.getString("warehouse_code"), r.getString("warehouse_name")),
            locationId == null ? null : new InboundResponse.NamedRef(locationId, r.getString("location_code"), r.getString("location_name")),
            unload, received, r.getString("fc_code"), r.getString("marking"), decimal(r, "pallet_qty"), decimal(r, "carton_qty"),
            decimal(r, "weight_lbs"), decimal(r, "cbm"), r.getInt("status"), statusName(r.getInt("status")), aging, r.getString("remark"),
            creatorId == null ? null : new InboundResponse.UserRef(creatorId, r.getString("creator_display_name")),
            offset(r, "created_at"), offset(r, "updated_at"), lotId != null, lotId);
    }
    private Long nullableLong(ResultSet r, String key) throws SQLException { long v = r.getLong(key); return r.wasNull() ? null : v; }
    private String decimal(ResultSet r, String key) throws SQLException { BigDecimal v = r.getBigDecimal(key); return v == null ? null : v.toPlainString(); }
    private OffsetDateTime offset(ResultSet r, String key) throws SQLException { try { return r.getObject(key, OffsetDateTime.class); } catch (SQLException e) { Timestamp t = r.getTimestamp(key); return t == null ? null : t.toInstant().atOffset(ZoneOffset.UTC); } }
    private String statusName(int value) { return switch (value) { case 0 -> "Pending"; case 1 -> "Unloading"; case 2 -> "Received"; case 3 -> "Put Away"; case 4 -> "Completed"; case 5 -> "Hold"; default -> String.valueOf(value); }; }
}

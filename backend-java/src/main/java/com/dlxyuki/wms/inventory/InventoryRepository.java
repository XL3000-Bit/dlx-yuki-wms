package com.dlxyuki.wms.inventory;

import com.dlxyuki.wms.user.UserAccount;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.sql.*;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.function.Function;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.*;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {
    private static final String SELECT = """
        select i.*, c.customer_code, c.customer_name, w.warehouse_code, w.warehouse_name,
               l.location_code, l.location_name
          from inventory_lots i
          left join customers c on c.id=i.customer_id
          join warehouses w on w.id=i.warehouse_id
          left join warehouse_locations l on l.id=i.location_id
        """;
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    public InventoryRepository(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = new NamedParameterJdbcTemplate(jdbc);
        this.objectMapper = objectMapper;
    }

    public InventoryListResponse list(InventoryQuery q, UserAccount user) {
        MapSqlParameterSource p = new MapSqlParameterSource();
        String where = filters(q, user, p);
        List<PriorityRule> rules = priorityRules();
        List<InventoryResponse> items = jdbc.query(SELECT + where, p, (r, n) -> map(r, rules));
        if (q.priorityLevel() != null) items.removeIf(x -> !q.priorityLevel().equals(x.priorityLevel()));
        if (q.agingMin() != null) items.removeIf(x -> x.agingDays() == null || x.agingDays() < q.agingMin());
        if (q.agingMax() != null) items.removeIf(x -> x.agingDays() == null || x.agingDays() > q.agingMax());
        items.sort(comparator(q.sortBy(), "asc".equals(q.sortOrder())));
        long total = items.size();
        int from = Math.min((q.page() - 1) * q.perPage(), items.size());
        int to = Math.min(from + q.perPage(), items.size());
        long pages = total == 0 ? 0 : (total + q.perPage() - 1) / q.perPage();
        return new InventoryListResponse(List.copyOf(items.subList(from, to)),
            new InventoryListResponse.PaginationMeta(q.page(), q.perPage(), total, pages));
    }

    public Optional<InventoryResponse> find(long id, UserAccount user) {
        MapSqlParameterSource p = new MapSqlParameterSource("id", id);
        String scope = scope(user, p);
        List<PriorityRule> rules = priorityRules();
        return jdbc.query(SELECT + " where i.id=:id" + scope, p, (r, n) -> map(r, rules)).stream().findFirst();
    }

    public List<InventoryTransactionResponse> transactions(long lotId) {
        String sql = """
            select t.*, fl.location_code from_code, fl.location_name from_name,
                   tl.location_code to_code, tl.location_name to_name,
                   u.display_name creator_name
              from inventory_transactions t
              left join warehouse_locations fl on fl.id=t.from_location_id
              left join warehouse_locations tl on tl.id=t.to_location_id
              join users u on u.id=t.created_by
             where t.inventory_lot_id=:lot_id
             order by t.created_at desc, t.id desc
            """;
        return jdbc.query(sql, Map.of("lot_id", lotId), (r, n) -> {
            Long fromId = nullableLong(r,"from_location_id"), toId = nullableLong(r,"to_location_id");
            return new InventoryTransactionResponse(r.getLong("id"), r.getString("transaction_type"),
                decimal(r,"pallet_delta"), decimal(r,"carton_delta"), decimal(r,"weight_delta"), decimal(r,"cbm_delta"),
                fromId == null ? null : new InventoryResponse.NamedRef(fromId,r.getString("from_code"),r.getString("from_name")),
                toId == null ? null : new InventoryResponse.NamedRef(toId,r.getString("to_code"),r.getString("to_name")),
                r.getString("reference_type"), nullableLong(r,"reference_id"), json(r,"before_snapshot"), json(r,"after_snapshot"),
                r.getString("remark"), new InventoryTransactionResponse.CreatedBy(r.getLong("created_by"),r.getString("creator_name")),
                offset(r,"created_at"));
        });
    }

    private String filters(InventoryQuery q, UserAccount user, MapSqlParameterSource p) {
        List<String> c = new ArrayList<>();
        addScope(user, p, c);
        if (q.q() != null) { p.addValue("q", "%" + q.q() + "%"); c.add("(i.lot_no ilike :q or i.container_number ilike :q or i.fc_code ilike :q or i.marking ilike :q or i.remark ilike :q)"); }
        if (q.containerNumber() != null) { p.addValue("container_number", "%" + q.containerNumber() + "%"); c.add("i.container_number ilike :container_number"); }
        if (q.fcCode() != null) { p.addValue("fc_code", "%" + q.fcCode() + "%"); c.add("i.fc_code ilike :fc_code"); }
        exact(c, p, "customer_id", q.customerId(), "i.customer_id=:customer_id");
        exact(c, p, "warehouse_id", q.warehouseId(), "i.warehouse_id=:warehouse_id");
        exact(c, p, "location_id", q.locationId(), "i.location_id=:location_id");
        exact(c, p, "status", q.status(), "i.status=:status");
        exact(c, p, "inbound_from", q.inboundDateFrom(), "i.inbound_date>=:inbound_from");
        exact(c, p, "inbound_to", q.inboundDateTo(), "i.inbound_date<=:inbound_to");
        if (q.hasAvailable() != null) c.add(q.hasAvailable()
            ? "(i.available_pallet_qty>0 or i.available_carton_qty>0)"
            : "(i.available_pallet_qty=0 and i.available_carton_qty=0)");
        return c.isEmpty() ? "" : " where " + String.join(" and ", c);
    }

    private void addScope(UserAccount u, MapSqlParameterSource p, List<String> clauses) {
        if (!"ADMIN".equals(u.role()) && "SELECTED".equals(u.warehouseScopeMode())) {
            if (u.warehouseIds().isEmpty()) clauses.add("false");
            else { p.addValue("scope_warehouses", u.warehouseIds()); clauses.add("i.warehouse_id in (:scope_warehouses)"); }
        }
        if (!"ADMIN".equals(u.role()) && "SELECTED".equals(u.customerScopeMode())) {
            if (u.customerIds().isEmpty()) clauses.add("false");
            else { p.addValue("scope_customers", u.customerIds()); clauses.add("i.customer_id in (:scope_customers)"); }
        }
    }
    private String scope(UserAccount u, MapSqlParameterSource p) { List<String> c = new ArrayList<>(); addScope(u, p, c); return c.isEmpty() ? "" : " and " + String.join(" and ", c); }
    private void exact(List<String> c, MapSqlParameterSource p, String key, Object value, String sql) { if (value != null) { p.addValue(key, value); c.add(sql); } }

    private List<PriorityRule> priorityRules() {
        return jdbc.query("select min_days,max_days,priority_level,priority_label from inventory_priority_rules where is_active order by sort_order desc", Map.of(),
            (r, n) -> new PriorityRule(r.getInt("min_days"), nullableInt(r, "max_days"), r.getString("priority_level"), r.getString("priority_label")));
    }

    private InventoryResponse map(ResultSet r, List<PriorityRule> rules) throws SQLException {
        LocalDate inbound = r.getObject("inbound_date", LocalDate.class);
        Integer aging = inbound == null ? null : (int)Math.max(0, ChronoUnit.DAYS.between(inbound, LocalDate.now(ZoneId.of("America/Los_Angeles"))));
        PriorityRule priority = aging == null ? null : rules.stream().filter(x -> x.matches(aging)).findFirst().orElse(null);
        Long customerId = nullableLong(r, "customer_id"), locationId = nullableLong(r, "location_id");
        return new InventoryResponse(r.getLong("id"), r.getString("lot_no"), r.getString("container_number"), r.getString("fc_code"), r.getString("marking"),
            customerId == null ? null : new InventoryResponse.NamedRef(customerId, r.getString("customer_code"), r.getString("customer_name")),
            new InventoryResponse.NamedRef(r.getLong("warehouse_id"), r.getString("warehouse_code"), r.getString("warehouse_name")),
            locationId == null ? null : new InventoryResponse.NamedRef(locationId, r.getString("location_code"), r.getString("location_name")),
            r.getLong("source_inbound_id"), inbound, aging, priority == null ? null : priority.level(), priority == null ? null : priority.label(),
            decimal(r,"original_pallet_qty"), decimal(r,"available_pallet_qty"), decimal(r,"allocated_pallet_qty"), decimal(r,"hold_pallet_qty"),
            decimal(r,"original_carton_qty"), decimal(r,"available_carton_qty"), decimal(r,"allocated_carton_qty"), decimal(r,"hold_carton_qty"),
            decimal(r,"original_weight_lbs"), decimal(r,"available_weight_lbs"), decimal(r,"allocated_weight_lbs"),
            decimal(r,"original_cbm"), decimal(r,"available_cbm"), decimal(r,"allocated_cbm"),
            r.getInt("status"), statusName(r.getInt("status")), r.getString("remark"), offset(r,"created_at"), offset(r,"updated_at"));
    }

    private Comparator<InventoryResponse> comparator(String field, boolean ascending) {
        Function<InventoryResponse, Comparable<?>> getter = switch (field) {
            case "id" -> x -> x.id(); case "lot_no" -> InventoryResponse::lotNo; case "container_number" -> InventoryResponse::containerNumber;
            case "fc_code" -> InventoryResponse::fcCode; case "marking" -> InventoryResponse::marking; case "source_inbound_id" -> x -> x.sourceInboundId();
            case "inbound_date" -> InventoryResponse::inboundDate; case "aging_days" -> InventoryResponse::agingDays; case "priority_level" -> InventoryResponse::priorityLevel;
            case "original_pallet_qty" -> x -> number(x.originalPalletQty()); case "available_pallet_qty" -> x -> number(x.availablePalletQty());
            case "allocated_pallet_qty" -> x -> number(x.allocatedPalletQty()); case "hold_pallet_qty" -> x -> number(x.holdPalletQty());
            case "original_carton_qty" -> x -> number(x.originalCartonQty()); case "available_carton_qty" -> x -> number(x.availableCartonQty());
            case "allocated_carton_qty" -> x -> number(x.allocatedCartonQty()); case "hold_carton_qty" -> x -> number(x.holdCartonQty());
            case "original_weight_lbs" -> x -> number(x.originalWeightLbs()); case "available_weight_lbs" -> x -> number(x.availableWeightLbs());
            case "allocated_weight_lbs" -> x -> number(x.allocatedWeightLbs()); case "original_cbm" -> x -> number(x.originalCbm());
            case "available_cbm" -> x -> number(x.availableCbm()); case "allocated_cbm" -> x -> number(x.allocatedCbm());
            case "status" -> x -> x.status(); case "status_name" -> InventoryResponse::statusName; case "remark" -> InventoryResponse::remark;
            case "created_at" -> InventoryResponse::createdAt; case "updated_at" -> InventoryResponse::updatedAt;
            default -> x -> 0;
        };
        Comparator<InventoryResponse> result = (a, b) -> compare(getter.apply(a), getter.apply(b));
        return ascending ? result : result.reversed();
    }
    @SuppressWarnings({"rawtypes", "unchecked"})
    private int compare(Comparable a, Comparable b) {
        Object av = a == null ? 0 : a, bv = b == null ? 0 : b;
        if (!av.getClass().equals(bv.getClass())) return String.valueOf(av).compareTo(String.valueOf(bv));
        return ((Comparable)av).compareTo(bv);
    }
    private BigDecimal number(String value) { return new BigDecimal(value); }
    private String decimal(ResultSet r, String key) throws SQLException { BigDecimal v = r.getBigDecimal(key); return v == null ? null : v.toPlainString(); }
    private Integer nullableInt(ResultSet r, String key) throws SQLException { int v = r.getInt(key); return r.wasNull() ? null : v; }
    private Long nullableLong(ResultSet r, String key) throws SQLException { long v = r.getLong(key); return r.wasNull() ? null : v; }
    private OffsetDateTime offset(ResultSet r, String key) throws SQLException { try { return r.getObject(key, OffsetDateTime.class); } catch (SQLException e) { Timestamp t = r.getTimestamp(key); return t == null ? null : t.toInstant().atOffset(ZoneOffset.UTC); } }
    private Map<String,Object> json(ResultSet r, String key) throws SQLException {
        String value = r.getString(key);
        if (value == null) return null;
        try { return objectMapper.readValue(value, new TypeReference<>() {}); }
        catch (Exception e) { throw new SQLException("Invalid JSON in " + key, e); }
    }
    private String statusName(int value) { return switch (value) { case 0 -> "Available"; case 1 -> "Partially Allocated"; case 2 -> "Fully Allocated"; case 3 -> "Hold"; case 4 -> "Depleted"; case 5 -> "Closed"; default -> String.valueOf(value); }; }
    private record PriorityRule(int min, Integer max, String level, String label) { boolean matches(int days) { return min <= days && (max == null || max >= days); } }
}

package com.dlxyuki.wms.dashboard;

import com.dlxyuki.wms.user.UserAccount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OperationsDashboardRepository {
    private static final String OPEN_WO = "('OPEN','ASSIGNED','IN_PROGRESS')";
    private static final String OPEN_EX = "('OPEN','INVESTIGATING')";
    private final NamedParameterJdbcTemplate jdbc;

    public OperationsDashboardRepository(JdbcTemplate jdbcTemplate) {
        this.jdbc = new NamedParameterJdbcTemplate(jdbcTemplate);
    }

    public Map<String, Object> build(UserAccount user, OffsetDateTime start, OffsetDateTime end,
                                     OffsetDateTime now, Long warehouseId) {
        Params p = new Params(user, start, end, now, warehouseId);
        long activeLoads = count("loads l", p.warehouse("l.warehouse_id") + " AND l.status::text IN ('PLANNED','READY','DISPATCHED')", p.args());
        String outboundScope = p.warehouse("o.warehouse_id") + p.customer("o.customer_id");
        long outboundReady = count("outbound_orders o", outboundScope + " AND o.status IN (3,4)", p.args());
        long outboundActive = count("outbound_orders o", outboundScope + " AND o.status IN (0,1,2,3,4,7)", p.args());
        String woScope = p.warehouse("w.warehouse_id");
        String exScope = p.warehouse("e.warehouse_id");
        long openWo = count("work_orders w", woScope + " AND w.status::text IN " + OPEN_WO, p.args());
        long openEx = count("operational_exceptions e", exScope + " AND e.status::text IN " + OPEN_EX, p.args());
        long critical = count("operational_exceptions e", exScope + " AND e.status::text IN " + OPEN_EX + " AND e.severity::text='CRITICAL'", p.args());
        long completedWo = count("work_orders w", woScope + " AND w.completed_at>=:start AND w.completed_at<:end", p.args());
        long periodLoads = count("loads l", p.warehouse("l.warehouse_id") + " AND l.created_at>=:start AND l.created_at<:end", p.args());
        long periodOutbounds = count("outbound_orders o JOIN loads l ON o.load_id=l.id", p.warehouse("l.warehouse_id") + " AND l.created_at>=:start AND l.created_at<:end", p.args());
        String woOpen = woScope + " AND w.status::text IN " + OPEN_WO;
        String exOpen = exScope + " AND e.status::text IN " + OPEN_EX;
        Map<String, Long> woStatus = groups("work_orders w", "w.status::text", woScope, p.args());
        Map<String, Long> woPriority = groups("work_orders w", "w.priority::text", woOpen, p.args());
        Map<String, Long> exStatus = groups("operational_exceptions e", "e.status::text", exScope, p.args());
        Map<String, Long> exSeverity = groups("operational_exceptions e", "e.severity::text", exOpen, p.args());
        Map<String, Long> exTypes = groups("operational_exceptions e", "e.exception_type::text", exOpen, p.args());
        long overdue = count("work_orders w", woOpen + " AND w.scheduled_at IS NOT NULL AND w.scheduled_at<:now", p.args());
        long resolved = count("operational_exceptions e", exScope + " AND e.status::text='RESOLVED' AND e.resolved_at>=:start AND e.resolved_at<:end", p.args());
        Double averageResolution = averageResolution(exScope, p.args());

        Map<String, Object> root = map();
        root.put("meta", map("generated_at", now, "period_start", start, "period_end_exclusive", end,
            "warehouse_id", warehouseId, "date_semantics", "Snapshot metrics ignore the date range; period metrics use [start, end)."));
        root.put("summary", map("active_loads", activeLoads, "outbound_ready", outboundReady,
            "outbound_active", outboundActive, "open_work_orders", openWo, "open_exceptions", openEx,
            "critical_open_exceptions", critical, "completed_work_orders_period", completedWo));
        root.put("loads", map("created_period", periodLoads,
            "created_period_by_current_status", groups("loads l", "l.status::text", p.warehouse("l.warehouse_id") + " AND l.created_at>=:start AND l.created_at<:end", p.args()),
            "active_snapshot", activeLoads, "average_outbounds_per_period_load", periodLoads == 0 ? null : round2((double) periodOutbounds / periodLoads)));
        root.put("work_orders", map("status_snapshot", woStatus, "open_priority_snapshot", woPriority,
            "completed_period", completedWo, "overdue_snapshot", overdue,
            "aging_snapshot", aging("work_orders w", "w.created_at", woOpen, new int[]{4,12,24}, new String[]{"lt_4h","4_12h","12_24h","gt_24h"}, p.args())));
        root.put("exceptions", map("status_snapshot", exStatus, "open_severity_snapshot", exSeverity,
            "open_type_snapshot", exTypes, "resolved_period", resolved,
            "average_resolution_hours_period", averageResolution,
            "aging_snapshot", aging("operational_exceptions e", "e.reported_at", exOpen, new int[]{4,12,24,72}, new String[]{"lt_4h","4_12h","12_24h","1_3d","gt_3d"}, p.args())));
        root.put("execution_funnel", List.of(
            map("stage", "OPEN", "count", woStatus.getOrDefault("OPEN", 0L)),
            map("stage", "ASSIGNED", "count", woStatus.getOrDefault("ASSIGNED", 0L)),
            map("stage", "IN_PROGRESS", "count", woStatus.getOrDefault("IN_PROGRESS", 0L)),
            map("stage", "COMPLETED", "count", woStatus.getOrDefault("COMPLETED", 0L))));
        root.put("warehouses", warehouses(p));
        root.put("attention", attention(p, woOpen, exOpen));
        root.put("recent_activity", recent(p, woScope, exScope));
        return root;
    }

    private long count(String from, String where, MapSqlParameterSource args) {
        Long value = jdbc.queryForObject("SELECT count(*) FROM " + from + " WHERE " + where, args, Long.class);
        return value == null ? 0 : value;
    }

    private Map<String, Long> groups(String from, String column, String where, MapSqlParameterSource args) {
        Map<String, Long> result = new LinkedHashMap<>();
        jdbc.query("SELECT " + column + " k,count(*) n FROM " + from + " WHERE " + where + " GROUP BY " + column,
            args, (org.springframework.jdbc.core.RowCallbackHandler) rs -> {
                result.put(rs.getString("k"), rs.getLong("n"));
            });
        return result;
    }

    private Double averageResolution(String exScope, MapSqlParameterSource args) {
        Double value = jdbc.queryForObject("SELECT avg(extract(epoch FROM (e.resolved_at-e.reported_at))/3600.0) FROM operational_exceptions e WHERE "
            + exScope + " AND e.status::text='RESOLVED' AND e.resolved_at>=:start AND e.resolved_at<:end", args, Double.class);
        return value == null ? null : round2(value);
    }

    private Map<String, Long> aging(String from, String column, String where, int[] hours, String[] labels, MapSqlParameterSource args) {
        StringBuilder sql = new StringBuilder("SELECT ");
        for (int i = 0; i <= hours.length; i++) {
            if (i > 0) sql.append(',');
            if (i == 0) sql.append("count(*) FILTER (WHERE ").append(column).append(">:age0)");
            else if (i == hours.length) sql.append("count(*) FILTER (WHERE ").append(column).append("<=:age").append(i - 1).append(')');
            else sql.append("count(*) FILTER (WHERE ").append(column).append("<=:age").append(i - 1).append(" AND ").append(column).append(">:age").append(i).append(')');
            sql.append(" a").append(i);
        }
        MapSqlParameterSource local = copy(args);
        OffsetDateTime now = (OffsetDateTime) local.getValue("now");
        for (int i = 0; i < hours.length; i++) local.addValue("age" + i, now.minusHours(hours[i]));
        return jdbc.queryForObject(sql + " FROM " + from + " WHERE " + where, local, (rs, row) -> {
            Map<String, Long> result = new LinkedHashMap<>();
            for (int i = 0; i < labels.length; i++) result.put(labels[i], rs.getLong("a" + i));
            return result;
        });
    }

    private List<Map<String, Object>> warehouses(Params p) {
        String scope = p.warehouse("wh.id");
        String sql = "SELECT wh.id,wh.warehouse_code,wh.warehouse_name," +
            "(SELECT count(*) FROM work_orders w WHERE w.warehouse_id=wh.id AND w.status::text IN " + OPEN_WO + ") open_work_orders," +
            "(SELECT count(*) FROM operational_exceptions e WHERE e.warehouse_id=wh.id AND e.status::text IN " + OPEN_EX + ") open_exceptions " +
            "FROM warehouses wh WHERE " + scope + " ORDER BY wh.warehouse_code";
        return jdbc.query(sql, p.args(), (rs, row) -> map("warehouse_id", rs.getLong("id"),
            "warehouse_code", rs.getString("warehouse_code"), "warehouse_name", rs.getString("warehouse_name"),
            "open_work_orders", rs.getLong("open_work_orders"), "open_exceptions", rs.getLong("open_exceptions")));
    }

    private List<Map<String, Object>> recent(Params p, String woScope, String exScope) {
        List<Map<String, Object>> rows = new ArrayList<>();
        rows.addAll(jdbc.query("SELECT ev.work_order_id entity_id,w.work_order_no reference,ev.event_type,coalesce(ev.message,ev.note) message,ev.created_at " +
            "FROM work_order_events ev JOIN work_orders w ON w.id=ev.work_order_id WHERE " + woScope + " ORDER BY ev.created_at DESC,ev.id DESC LIMIT 10",
            p.args(), (rs, row) -> activity("WORK_ORDER", rs)));
        rows.addAll(jdbc.query("SELECT ev.operational_exception_id entity_id,e.exception_no reference,ev.event_type,ev.message,ev.created_at " +
            "FROM operational_exception_events ev JOIN operational_exceptions e ON e.id=ev.operational_exception_id WHERE " + exScope + " ORDER BY ev.created_at DESC,ev.id DESC LIMIT 10",
            p.args(), (rs, row) -> activity("EXCEPTION", rs)));
        rows.sort(Comparator.comparing(x -> (OffsetDateTime) x.get("created_at"), Comparator.reverseOrder()));
        return rows.size() > 15 ? new ArrayList<>(rows.subList(0, 15)) : rows;
    }

    private Map<String, Object> activity(String kind, ResultSet rs) throws SQLException {
        return map("kind", kind, "entity_id", rs.getLong("entity_id"), "reference", rs.getString("reference"),
            "event_type", rs.getString("event_type"), "message", rs.getString("message"), "created_at", time(rs, "created_at"));
    }

    private List<Map<String, Object>> attention(Params p, String woOpen, String exOpen) {
        List<Map<String, Object>> candidates = new ArrayList<>();
        candidates.addAll(jdbc.query("SELECT e.id,e.exception_no reference,e.title label,e.reported_at since FROM operational_exceptions e WHERE " + exOpen +
            " AND e.severity::text='CRITICAL' ORDER BY e.reported_at LIMIT 5", p.args(), (rs, row) ->
            map("kind","EXCEPTION","entity_id",rs.getLong("id"),"reference",rs.getString("reference"),"label",rs.getString("label"),"reason","Critical open exception","since",time(rs,"since"))));
        candidates.addAll(workOrderAttention(p, woOpen + " AND w.priority::text='URGENT'", "Urgent work order"));
        MapSqlParameterSource oldArgs = copy(p.args()).addValue("old_cutoff", p.now.minusHours(24));
        candidates.addAll(jdbc.query("SELECT w.id,w.work_order_no reference,w.status::text label,w.created_at since FROM work_orders w WHERE " + woOpen +
            " AND w.created_at<=:old_cutoff ORDER BY w.created_at LIMIT 5", oldArgs, (rs, row) -> attentionRow(rs, "Open longer than 24 hours")));
        List<Map<String, Object>> result = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (Map<String, Object> item : candidates) {
            if (seen.add(item.get("kind") + ":" + item.get("entity_id"))) result.add(item);
            if (result.size() == 12) break;
        }
        return result;
    }

    private List<Map<String, Object>> workOrderAttention(Params p, String where, String reason) {
        return jdbc.query("SELECT w.id,w.work_order_no reference,w.status::text label,w.created_at since FROM work_orders w WHERE " + where +
            " ORDER BY w.created_at LIMIT 5", p.args(), (rs, row) -> attentionRow(rs, reason));
    }

    private Map<String, Object> attentionRow(ResultSet rs, String reason) throws SQLException {
        return map("kind","WORK_ORDER","entity_id",rs.getLong("id"),"reference",rs.getString("reference"),
            "label",rs.getString("label"),"reason",reason,"since",time(rs,"since"));
    }

    private static OffsetDateTime time(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant().atOffset(ZoneOffset.UTC);
    }

    private static double round2(double value) { return Math.round(value * 100.0) / 100.0; }

    private static MapSqlParameterSource copy(MapSqlParameterSource source) {
        MapSqlParameterSource result = new MapSqlParameterSource();
        for (String name : source.getParameterNames()) result.addValue(name, source.getValue(name));
        return result;
    }

    private static LinkedHashMap<String, Object> map(Object... values) {
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        for (int i = 0; i < values.length; i += 2) result.put((String) values[i], values[i + 1]);
        return result;
    }

    private static final class Params {
        private final UserAccount user;
        private final Long warehouseId;
        private final MapSqlParameterSource args;
        private final OffsetDateTime now;

        Params(UserAccount user, OffsetDateTime start, OffsetDateTime end, OffsetDateTime now, Long warehouseId) {
            this.user = user;
            this.warehouseId = warehouseId;
            this.now = now;
            this.args = new MapSqlParameterSource().addValue("start", start).addValue("end", end).addValue("now", now).addValue("warehouse_id", warehouseId);
            if (user.warehouseIds() != null && !user.warehouseIds().isEmpty()) args.addValue("warehouse_ids", user.warehouseIds());
            if (user.customerIds() != null && !user.customerIds().isEmpty()) args.addValue("customer_ids", user.customerIds());
        }

        MapSqlParameterSource args() { return args; }
        String warehouse(String column) {
            List<String> clauses = new ArrayList<>();
            if (!"ADMIN".equalsIgnoreCase(user.role()) && !"ALL".equalsIgnoreCase(user.warehouseScopeMode()))
                clauses.add(user.warehouseIds() == null || user.warehouseIds().isEmpty() ? "FALSE" : column + " IN (:warehouse_ids)");
            if (warehouseId != null) clauses.add(column + "=:warehouse_id");
            return clauses.isEmpty() ? "TRUE" : String.join(" AND ", clauses);
        }
        String customer(String column) {
            if ("ADMIN".equalsIgnoreCase(user.role()) || "ALL".equalsIgnoreCase(user.customerScopeMode())) return "";
            return user.customerIds() == null || user.customerIds().isEmpty() ? " AND FALSE" : " AND " + column + " IN (:customer_ids)";
        }
    }
}

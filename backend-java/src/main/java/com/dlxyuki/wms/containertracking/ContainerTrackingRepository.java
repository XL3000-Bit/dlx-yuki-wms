package com.dlxyuki.wms.containertracking;

import com.dlxyuki.wms.config.AppProperties;
import com.dlxyuki.wms.user.UserAccount;
import java.math.*;
import java.sql.*;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.namedparam.*;
import org.springframework.stereotype.Repository;

@Repository
class ContainerTrackingRepository {
  private final NamedParameterJdbcTemplate jdbc;
  private final ZoneId zone;

  ContainerTrackingRepository(NamedParameterJdbcTemplate j, AppProperties p) {
    jdbc = j;
    zone = ZoneId.of(p.businessTimezone() == null ? "America/Los_Angeles" : p.businessTimezone());
  }

  private static final String AGG =
      "select upper(i.container_number) container_key,min(o.schedule_pickup_at)"
          + " earliest_outbound_at,min(i.inbound_date) inbound_date from inventory_lots i join"
          + " outbound_inventory_allocations a on a.inventory_lot_id=i.id join outbound_orders o on"
          + " o.id=a.outbound_order_id where i.container_number is not null and o.status"
          + " in(0,1,2,3,4,7) and o.schedule_pickup_at is not null and"
          + " a.allocated_pallet_qty>a.completed_pallet_qty %s group by upper(i.container_number)";

  Object list(ContainerTrackingQuery q, UserAccount u) {
    var p = new MapSqlParameterSource();
    var f = new ArrayList<String>();
    warehouseScope(u, p, f, "ct.warehouse_id", "tw");
    if (q.q() != null && !q.q().isEmpty()) {
      p.addValue("q", "%" + q.q() + "%");
      f.add(
          "(ct.container_number ilike :q or ct.mbl_number ilike :q or ct.hbl_number ilike :q or"
              + " ct.customer_reference ilike :q or ct.delivery_warehouse_raw ilike :q)");
    }
    if (q.status() != null) {
      p.addValue("status", q.status());
      f.add("ct.tracking_status::text=:status");
    }
    if (q.warehouseId() != null && q.warehouseId() != 0) {
      p.addValue("warehouse", q.warehouseId());
      f.add("ct.warehouse_id=:warehouse");
    }
    LocalDate today = LocalDate.now(zone), start = null, end = null;
    if ("overdue".equals(q.outboundWindow())) end = today.minusDays(1);
    else if ("today".equals(q.outboundWindow())) start = end = today;
    else if ("tomorrow".equals(q.outboundWindow())) start = end = today.plusDays(1);
    else if ("next_3".equals(q.outboundWindow())) {
      start = today;
      end = today.plusDays(3);
    } else if ("next_7".equals(q.outboundWindow())) {
      start = today;
      end = today.plusDays(7);
    } else if ("none".equals(q.outboundWindow())) f.add("ag.earliest_outbound_at is null");
    start = q.outboundFrom() != null ? q.outboundFrom() : start;
    end = q.outboundTo() != null ? q.outboundTo() : end;
    if (start != null) {
      p.addValue("from", Timestamp.from(start.atStartOfDay(zone).toInstant()));
      f.add("ag.earliest_outbound_at>=:from");
    }
    if (end != null) {
      p.addValue("to", Timestamp.from(end.plusDays(1).atStartOfDay(zone).toInstant()));
      f.add("ag.earliest_outbound_at<:to");
    }
    String sql =
        "select ct.*,ag.earliest_outbound_at,ag.inbound_date dispatch_inbound_date from"
            + " container_trackings ct left join ("
            + aggregate(u, p)
            + ") ag on ag.container_key=upper(ct.container_number)"
            + where(f);
    var rows = jdbc.query(sql, p, (r, n) -> row(r));
    if (q.dispatchPriority() != null)
      rows.removeIf(
          x -> !q.dispatchPriority().toUpperCase(Locale.ROOT).equals(x.get("dispatch_priority")));
    sort(rows, q.sortBy(), q.sortOrder());
    int total = rows.size(),
        from = Math.min((q.page() - 1) * q.perPage(), total),
        to = Math.min(from + q.perPage(), total);
    var out = new LinkedHashMap<String, Object>();
    out.put("data", List.copyOf(rows.subList(from, to)));
    out.put(
        "meta",
        Map.of(
            "page",
            q.page(),
            "per_page",
            q.perPage(),
            "total",
            total,
            "total_pages",
            (total + q.perPage() - 1) / q.perPage()));
    return out;
  }

  Optional<Map<String, Object>> detail(long id, UserAccount u) {
    var p = new MapSqlParameterSource("id", id);
    var f = new ArrayList<>(List.of("ct.id=:id"));
    warehouseScope(u, p, f, "ct.warehouse_id", "tw");
    var found =
        jdbc.query(
            "select ct.*,null::timestamptz earliest_outbound_at,null::date dispatch_inbound_date"
                + " from container_trackings ct"
                + where(f),
            p,
            (r, n) -> row(r));
    if (found.isEmpty()) return Optional.empty();
    var basic = found.get(0);
    String c = (String) basic.get("container_number");
    var inbound = inbounds(c, u);
    var lots = lots(c, u);
    var d = dispatch(c, u);
    LocalDate fallback =
        inbound.stream()
            .map(x -> (LocalDate) x.get("_date"))
            .filter(Objects::nonNull)
            .min(LocalDate::compareTo)
            .orElse(null);
    dispatchFields(basic, d.earliest, d.inbound != null ? d.inbound : fallback);
    var tasks = tasks(c, u);
    var related = new ArrayList<Map<String, Object>>();
    BigDecimal allocated = BigDecimal.ZERO, completed = BigDecimal.ZERO;
    var active = new ArrayList<Task>();
    for (var t : tasks) {
      allocated = allocated.add(t.allocated);
      completed = completed.add(t.completed);
      if (t.status != 5 && t.status != 6 && t.allocated.compareTo(t.completed) > 0) active.add(t);
      related.add(t.data);
    }
    Integer s;
    if (active.stream().anyMatch(t -> t.status == 7)) {
      s = 7;
    } else if (!tasks.isEmpty() && active.isEmpty()) {
      s = 5;
    } else if (active.isEmpty()) {
      s = null;
    } else {
      s = active.get(0).status;
    }
    BigDecimal capacity =
        lots.stream()
            .map(
                x ->
                    new BigDecimal((String) x.get("available_pallet_qty"))
                        .add(new BigDecimal((String) x.get("allocated_pallet_qty"))))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    basic.put(
        "dispatch_readiness",
        readiness(
            s,
            !lots.isEmpty() && capacity.signum() > 0,
            !tasks.isEmpty(),
            allocated,
            completed,
            capacity));
    inbound.forEach(x -> x.remove("_date"));
    var out = new LinkedHashMap<String, Object>();
    out.put("basic", basic);
    out.put("inbound", inbound);
    out.put("inventory_lots", lots);
    out.put("related_outbound_tasks", related);
    out.put("anomalies", List.of());
    return Optional.of(out);
  }

  private List<Map<String, Object>> inbounds(String c, UserAccount u) {
    var p = new MapSqlParameterSource("c", c);
    var f = new ArrayList<>(List.of("upper(container_number)=upper(:c)"));
    scope(u, p, f, "warehouse_id", "customer_id", "iw", "ic");
    return jdbc.query(
        "select id,fc_code,pallet_qty,carton_qty,weight_lbs,cbm,received_date,unload_date from"
            + " inbound_records"
            + where(f),
        p,
        (r, n) -> {
          var x = new LinkedHashMap<String, Object>();
          x.put("id", r.getLong("id"));
          x.put("fc_code", r.getString("fc_code"));
          for (String k : List.of("pallet_qty", "carton_qty", "weight_lbs", "cbm"))
            x.put(k, dec(r, k));
          java.sql.Date rd = r.getDate("received_date"), ud = r.getDate("unload_date");
          x.put("_date", rd != null ? rd.toLocalDate() : ud == null ? null : ud.toLocalDate());
          return x;
        });
  }

  private List<Map<String, Object>> lots(String c, UserAccount u) {
    var p = new MapSqlParameterSource("c", c);
    var f = new ArrayList<>(List.of("upper(container_number)=upper(:c)"));
    scope(u, p, f, "warehouse_id", "customer_id", "lw", "lc");
    return jdbc.query(
        "select id,lot_no,status,available_pallet_qty,allocated_pallet_qty from inventory_lots"
            + where(f),
        p,
        (r, n) -> {
          var x = new LinkedHashMap<String, Object>();
          x.put("id", r.getLong("id"));
          x.put("lot_no", r.getString("lot_no"));
          x.put("status", r.getObject("status"));
          x.put("available_pallet_qty", dec(r, "available_pallet_qty"));
          x.put("allocated_pallet_qty", dec(r, "allocated_pallet_qty"));
          return x;
        });
  }

  private Dispatch dispatch(String c, UserAccount u) {
    var p = new MapSqlParameterSource("c", c);
    return jdbc
        .query(
            "select earliest_outbound_at,inbound_date from ("
                + aggregate(u, p)
                + ") x where container_key=upper(:c)",
            p,
            (r, n) -> new Dispatch(inst(r, "earliest_outbound_at"), date(r, "inbound_date")))
        .stream()
        .findFirst()
        .orElse(new Dispatch(null, null));
  }

  private List<Task> tasks(String c, UserAccount u) {
    var p = new MapSqlParameterSource("c", c);
    var f = new ArrayList<>(List.of("upper(i.container_number)=upper(:c)", "o.status<>6"));
    scope(u, p, f, "o.warehouse_id", "o.customer_id", "ow", "oc");
    String sql =
        "select o.id outbound_id,o.ob_no,coalesce(o.fc_code,i.fc_code)"
            + " fc_code,o.schedule_pickup_at,o.status,a.allocated_pallet_qty,a.completed_pallet_qty,(select"
            + " status from picking_lists where outbound_order_id=o.id order by id desc limit 1)"
            + " picking_status,(select id from bols where outbound_order_id=o.id order by id desc"
            + " limit 1) bol_id,(select bol_no from bols where outbound_order_id=o.id order by id"
            + " desc limit 1) bol_no,(select status from bols where outbound_order_id=o.id order by"
            + " id desc limit 1) bol_status from outbound_orders o join"
            + " outbound_inventory_allocations a on a.outbound_order_id=o.id join inventory_lots i"
            + " on i.id=a.inventory_lot_id "
            + where(f)
            + " order by o.schedule_pickup_at asc nulls last";
    return jdbc.query(sql, p, (r, n) -> task(r));
  }

  private Task task(ResultSet r) throws SQLException {
    int s = r.getInt("status");
    BigDecimal a = bd(r, "allocated_pallet_qty"), c = bd(r, "completed_pallet_qty");
    var x = new LinkedHashMap<String, Object>();
    x.put("outbound_id", r.getLong("outbound_id"));
    x.put("ob_no", r.getString("ob_no"));
    x.put("fc_code", r.getString("fc_code"));
    Instant time = inst(r, "schedule_pickup_at");
    x.put("outbound_date", time == null ? null : time.atZone(zone).toLocalDate());
    x.put("pallet_qty", a.toPlainString());
    x.put("completed_pallet_qty", c.toPlainString());
    x.put("status", s);
    x.put(
        "status_name",
        List.of(
                "NEW",
                "HOLD",
                "IN_PROGRESS",
                "CONFIRMED",
                "DISPATCHED",
                "COMPLETED",
                "CANCELED",
                "EXCEPTION")
            .get(s));
    x.put("picking_status", r.getObject("picking_status"));
    x.put("bol_id", nlong(r, "bol_id"));
    x.put("bol_no", r.getString("bol_no"));
    x.put("bol_status", r.getObject("bol_status"));
    return new Task(s, a, c, x);
  }

  private Map<String, Object> row(ResultSet r) throws SQLException {
    var x = new LinkedHashMap<String, Object>();
    x.put("id", r.getLong("id"));
    for (String k : List.of("container_number", "mbl_number", "hbl_number"))
      x.put(k, r.getString(k));
    for (String k : List.of("pod_eta", "ir_eta")) x.put(k, time(r, k));
    for (String k : List.of("pod", "delivery_location", "delivery_warehouse_raw"))
      x.put(k, r.getString(k));
    for (String k :
        List.of(
            "scheduled_delivery_at",
            "actual_delivery_at",
            "wa_received_at",
            "wa_empty_at",
            "wa_complete_at")) x.put(k, time(r, k));
    x.put("tracking_status", r.getString("tracking_status"));
    x.put("is_received", r.getTimestamp("wa_received_at") != null);
    x.put("is_empty", r.getTimestamp("wa_empty_at") != null);
    x.put("is_complete", r.getTimestamp("wa_complete_at") != null);
    x.put("anomalies", List.of());
    x.put("source_file_name", r.getString("source_file_name"));
    x.put("source_row_number", r.getObject("source_row_number"));
    dispatchFields(x, inst(r, "earliest_outbound_at"), date(r, "dispatch_inbound_date"));
    return x;
  }

  private void dispatchFields(Map<String, Object> x, Instant e, LocalDate inbound) {
    LocalDate today = LocalDate.now(zone), out = e == null ? null : e.atZone(zone).toLocalDate();
    Integer remain = out == null ? null : (int) (out.toEpochDay() - today.toEpochDay()),
        days =
            inbound == null ? null : (int) Math.max(0, today.toEpochDay() - inbound.toEpochDay());
    String priority =
        remain == null || remain > 5
            ? "NORMAL"
            : remain <= 0 ? "CRITICAL" : remain <= 2 ? "HIGH" : "MEDIUM";
    x.put("inbound_date", inbound);
    x.put("warehouse_days", days);
    x.put("earliest_outbound_date", out);
    x.put("outbound_days_remaining", remain);
    x.put("dispatch_priority", priority);
    x.put(
        "dispatch_priority_rank",
        Map.of("CRITICAL", 0, "HIGH", 1, "MEDIUM", 2, "NORMAL", 3).get(priority));
  }

  private String readiness(
      Integer s,
      boolean inventory,
      boolean allocation,
      BigDecimal a,
      BigDecimal c,
      BigDecimal capacity) {
    if (Objects.equals(s, 7)) return "BLOCKED";
    if (Objects.equals(s, 5) || (allocation && a.signum() > 0 && c.compareTo(a) >= 0))
      return "COMPLETED";
    if (Objects.equals(s, 6) || !inventory || !allocation || a.signum() <= 0) return "NOT_READY";
    BigDecimal remaining = a.subtract(c).max(BigDecimal.ZERO);
    if (capacity.compareTo(remaining) < 0) return "NOT_READY";
    if (c.signum() > 0 && c.compareTo(a) < 0) return "PARTIAL";
    return "READY";
  }

  private String aggregate(UserAccount u, MapSqlParameterSource p) {
    var f = new ArrayList<String>();
    scope(u, p, f, "o.warehouse_id", "o.customer_id", "aw", "ac");
    scope(u, p, f, "i.warehouse_id", "i.customer_id", "alw", "alc");
    return AGG.formatted(f.isEmpty() ? "" : " and " + String.join(" and ", f));
  }

  private void warehouseScope(
      UserAccount u, MapSqlParameterSource p, List<String> f, String col, String key) {
    if (!"ADMIN".equals(u.role()) && "SELECTED".equals(u.warehouseScopeMode())) {
      if (u.warehouseIds().isEmpty()) f.add("false");
      else {
        p.addValue(key, u.warehouseIds());
        f.add(col + " in (:" + key + ")");
      }
    }
  }

  private void scope(
      UserAccount u,
      MapSqlParameterSource p,
      List<String> f,
      String wc,
      String cc,
      String wk,
      String ck) {
    warehouseScope(u, p, f, wc, wk);
    if (!"ADMIN".equals(u.role()) && "SELECTED".equals(u.customerScopeMode())) {
      if (u.customerIds().isEmpty()) f.add("false");
      else {
        p.addValue(ck, u.customerIds());
        f.add(cc + " in (:" + ck + ")");
      }
    }
  }

  @SuppressWarnings({"rawtypes", "unchecked"})
  private void sort(List<Map<String, Object>> r, String requested, String order) {
    String key =
        Map.of(
                "earliest_outbound_date",
                "earliest_outbound_date",
                "outbound_days_remaining",
                "outbound_days_remaining",
                "warehouse_days",
                "warehouse_days",
                "dispatch_priority",
                "dispatch_priority_rank",
                "pod_eta",
                "pod_eta")
            .getOrDefault(requested, "pod_eta");
    Comparator<Map<String, Object>> c =
        (a, b) -> {
          Object x = a.get(key), y = b.get(key);
          if (x == null) return y == null ? 0 : -1;
          if (y == null) return 1;
          return ((Comparable) x).compareTo(y);
        };
    if (!"asc".equals(order)) c = c.reversed();
    r.sort(c);
  }

  private String where(List<String> f) {
    return f.isEmpty() ? "" : " where " + String.join(" and ", f);
  }

  private BigDecimal bd(ResultSet r, String k) throws SQLException {
    return Optional.ofNullable(r.getBigDecimal(k)).orElse(BigDecimal.ZERO);
  }

  private String dec(ResultSet r, String k) throws SQLException {
    BigDecimal d = r.getBigDecimal(k);
    return d == null ? null : d.toPlainString();
  }

  private Instant inst(ResultSet r, String k) throws SQLException {
    Timestamp t = r.getTimestamp(k);
    return t == null ? null : t.toInstant();
  }

  private Object time(ResultSet r, String k) throws SQLException {
    Instant i = inst(r, k);
    return i == null ? null : i.atOffset(ZoneOffset.UTC);
  }

  private LocalDate date(ResultSet r, String k) throws SQLException {
    java.sql.Date d = r.getDate(k);
    return d == null ? null : d.toLocalDate();
  }

  private Long nlong(ResultSet r, String k) throws SQLException {
    long v = r.getLong(k);
    return r.wasNull() ? null : v;
  }

  private record Dispatch(Instant earliest, LocalDate inbound) {}

  private record Task(
      int status, BigDecimal allocated, BigDecimal completed, Map<String, Object> data) {}
}

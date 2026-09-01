package com.dlxyuki.wms.notification;

import com.dlxyuki.wms.user.UserAccount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class NotificationRepository {
    private final NamedParameterJdbcTemplate jdbc;
    NotificationRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }

    Object list(int page, int size, boolean unreadOnly, UserAccount user) {
        MapSqlParameterSource p = params(user);
        List<String> filters = filters(user, p);
        if (unreadOnly) filters.add("n.is_read=false");
        String where = " where " + String.join(" and ", filters);
        Integer total = jdbc.queryForObject("select count(*) from operational_notifications n" + where, p, Integer.class);
        p.addValue("limit", size).addValue("offset", (page - 1) * size);
        List<Map<String,Object>> data = jdbc.query("select n.id,n.notification_type::text as type,n.severity::text as severity,n.title,n.message,n.warehouse_id,n.source_type,n.source_id,n.reference,n.target_route,n.is_read,n.read_at,n.created_at,n.expires_at from operational_notifications n" + where + " order by n.created_at desc,n.id desc limit :limit offset :offset", p, this::row);
        int count = total == null ? 0 : total;
        Map<String,Object> meta = new LinkedHashMap<>();
        meta.put("page", page); meta.put("per_page", size); meta.put("total", count); meta.put("total_pages", (count + size - 1) / size);
        Map<String,Object> result = new LinkedHashMap<>(); result.put("data", data); result.put("meta", meta); return result;
    }

    Object unreadCount(UserAccount user) {
        MapSqlParameterSource p = params(user); List<String> filters = filters(user, p); filters.add("n.is_read=false");
        Integer count = jdbc.queryForObject("select count(*) from operational_notifications n where " + String.join(" and ", filters), p, Integer.class);
        return Map.of("count", count == null ? 0 : count);
    }

    private MapSqlParameterSource params(UserAccount user) { return new MapSqlParameterSource("user_id", user.id()); }
    private List<String> filters(UserAccount user, MapSqlParameterSource p) {
        List<String> f = new ArrayList<>(List.of("n.user_id=:user_id", "n.is_active=true", "(n.expires_at is null or n.expires_at>=current_timestamp)"));
        if (!"ADMIN".equalsIgnoreCase(user.role()) && "SELECTED".equalsIgnoreCase(user.warehouseScopeMode())) {
            if (user.warehouseIds().isEmpty()) f.add("false");
            else { p.addValue("scope_warehouses", user.warehouseIds()); f.add("n.warehouse_id in (:scope_warehouses)"); }
        }
        return f;
    }
    private Map<String,Object> row(ResultSet r, int ignored) throws SQLException {
        Map<String,Object> x = new LinkedHashMap<>();
        for (String key : List.of("id","type","severity","title","message","warehouse_id","source_type","source_id","reference","target_route","is_read","read_at","created_at","expires_at")) x.put(key, r.getObject(key));
        return x;
    }
}

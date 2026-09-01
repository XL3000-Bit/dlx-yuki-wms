package com.dlxyuki.wms.user;

import java.util.List;
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class UserRepository {
    private final JdbcTemplate jdbc;
    public UserRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Optional<UserAccount> findByUsernameOrEmail(String login) {
        return query("select id, created_at, updated_at, username, display_name, email, password_hash, role::text, is_active, warehouse_scope_mode::text, customer_scope_mode::text from users where username = ? or email = ? limit 1", login, login);
    }

    public Optional<UserAccount> findById(long id) {
        return query("select id, created_at, updated_at, username, display_name, email, password_hash, role::text, is_active, warehouse_scope_mode::text, customer_scope_mode::text from users where id = ?", id);
    }

    public List<UserAccount> findAll() {
        return jdbc.query("select id, created_at, updated_at, username, display_name, email, password_hash, role::text, is_active, warehouse_scope_mode::text, customer_scope_mode::text from users order by id desc", (rs, row) -> map(rs));
    }

    public long count() {
        Long count = jdbc.queryForObject("select count(*) from users", Long.class);
        return count == null ? 0 : count;
    }

    public boolean existsByUsernameOrEmail(String username, String email) {
        return Boolean.TRUE.equals(jdbc.queryForObject("select exists(select 1 from users where username = ? or email = ?)", Boolean.class, username, email));
    }

    @Transactional
    public UserAccount create(String username, String displayName, String email, String hash, String role,
                              String warehouseMode, String customerMode, List<Long> warehouseIds, List<Long> customerIds) {
        Long id = jdbc.queryForObject("insert into users (username, display_name, email, password_hash, role, is_active, warehouse_scope_mode, customer_scope_mode) values (?, ?, ?, ?, cast(? as user_role), true, cast(? as scope_mode), cast(? as scope_mode)) returning id",
            Long.class, username, displayName, email, hash, role, warehouseMode, customerMode);
        replaceScopes(id, warehouseIds, customerIds);
        return findById(id).orElseThrow();
    }

    @Transactional
    public UserAccount update(long id, String displayName, String email, String hash, String role, Boolean active) {
        jdbc.update("update users set display_name=coalesce(?,display_name), email=coalesce(?,email), password_hash=coalesce(?,password_hash), role=coalesce(cast(? as user_role),role), is_active=coalesce(?,is_active), updated_at=now() where id=?",
            displayName, email, hash, role, active, id);
        return findById(id).orElseThrow();
    }

    @Transactional
    public UserAccount updateScope(long id, String warehouseMode, String customerMode, List<Long> warehouseIds, List<Long> customerIds) {
        jdbc.update("update users set warehouse_scope_mode=cast(? as scope_mode), customer_scope_mode=cast(? as scope_mode), updated_at=now() where id=?", warehouseMode, customerMode, id);
        replaceScopes(id, warehouseIds, customerIds);
        return findById(id).orElseThrow();
    }

    public boolean scopesExist(List<Long> warehouseIds, List<Long> customerIds) {
        int warehouses = countIds("warehouses", warehouseIds);
        int customers = countIds("customers", customerIds);
        return warehouses == warehouseIds.stream().distinct().count() && customers == customerIds.stream().distinct().count();
    }

    private int countIds(String table, List<Long> ids) {
        List<Long> distinct = ids.stream().distinct().toList();
        if (distinct.isEmpty()) return 0;
        String placeholders = String.join(",", java.util.Collections.nCopies(distinct.size(), "?"));
        Integer count = jdbc.queryForObject("select count(*) from " + table + " where id in (" + placeholders + ")",
            Integer.class, distinct.toArray());
        return count == null ? 0 : count;
    }

    private void replaceScopes(long userId, List<Long> warehouseIds, List<Long> customerIds) {
        jdbc.update("delete from user_warehouse_scopes where user_id=?", userId);
        jdbc.update("delete from user_customer_scopes where user_id=?", userId);
        warehouseIds.stream().distinct().forEach(id -> jdbc.update("insert into user_warehouse_scopes(user_id,warehouse_id) values (?,?)", userId, id));
        customerIds.stream().distinct().forEach(id -> jdbc.update("insert into user_customer_scopes(user_id,customer_id) values (?,?)", userId, id));
    }

    private Optional<UserAccount> query(String sql, Object... args) {
        try {
            return Optional.ofNullable(jdbc.queryForObject(sql, (rs, row) -> map(rs), args));
        } catch (EmptyResultDataAccessException ignored) { return Optional.empty(); }
    }

    private UserAccount map(java.sql.ResultSet rs) throws java.sql.SQLException {
        long id = rs.getLong("id");
        return new UserAccount(id, rs.getTimestamp("created_at").toInstant(), rs.getTimestamp("updated_at").toInstant(),
            rs.getString("username"), rs.getString("display_name"), rs.getString("email"), rs.getString("password_hash"),
            rs.getString("role"), rs.getBoolean("is_active"), rs.getString("warehouse_scope_mode"), rs.getString("customer_scope_mode"),
            ids("user_warehouse_scopes", "warehouse_id", id), ids("user_customer_scopes", "customer_id", id));
    }

    private List<Long> ids(String table, String column, long userId) {
        return jdbc.queryForList("select " + column + " from " + table + " where user_id = ? order by " + column, Long.class, userId);
    }
}

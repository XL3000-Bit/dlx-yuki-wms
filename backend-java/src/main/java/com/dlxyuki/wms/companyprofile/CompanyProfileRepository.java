package com.dlxyuki.wms.companyprofile;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class CompanyProfileRepository {
    private final JdbcTemplate jdbc;
    CompanyProfileRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    Optional<Map<String,Object>> first() {
        return jdbc.query("select id,created_at,updated_at,company_name,brand_name,legal_name,email,phone,address,city,state,zip_code,country,timezone,default_warehouse_id from company_profiles order by id limit 1",
            this::row).stream().findFirst();
    }

    private Map<String,Object> row(ResultSet r, int ignored) throws SQLException {
        Map<String,Object> value = new LinkedHashMap<>();
        for (String key : new String[]{"id","created_at","updated_at","company_name","brand_name","legal_name","email","phone","address","city","state","zip_code","country","timezone","default_warehouse_id"}) {
            value.put(key, r.getObject(key));
        }
        return value;
    }
}

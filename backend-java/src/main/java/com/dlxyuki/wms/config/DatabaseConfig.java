package com.dlxyuki.wms.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class DatabaseConfig {
    @Bean(destroyMethod = "close")
    DataSource dataSource(AppProperties properties) {
        URI uri = URI.create(properties.databaseUrl().replaceFirst("^postgresql\\+psycopg://", "postgresql://"));
        if (!"postgresql".equals(uri.getScheme()) || uri.getHost() == null) throw new IllegalArgumentException("DATABASE_URL must use PostgreSQL");
        String[] credentials = uri.getRawUserInfo() == null ? new String[0] : uri.getRawUserInfo().split(":", 2);
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:postgresql://" + uri.getHost() + ":" + (uri.getPort() < 0 ? 5432 : uri.getPort()) + uri.getPath() + (uri.getRawQuery() == null ? "" : "?" + uri.getRawQuery()));
        if (credentials.length > 0) config.setUsername(decode(credentials[0]));
        if (credentials.length > 1) config.setPassword(decode(credentials[1]));
        config.setPoolName("dlx-yuki-wms");
        config.setMaximumPoolSize(10);
        HikariDataSource dataSource = new HikariDataSource();
        dataSource.setJdbcUrl(config.getJdbcUrl());
        dataSource.setUsername(config.getUsername());
        dataSource.setPassword(config.getPassword());
        dataSource.setPoolName(config.getPoolName());
        dataSource.setMaximumPoolSize(config.getMaximumPoolSize());
        return dataSource;
    }

    @Bean JdbcTemplate jdbcTemplate(DataSource dataSource) { return new JdbcTemplate(dataSource); }
    private static String decode(String value) { return URLDecoder.decode(value, StandardCharsets.UTF_8); }
}

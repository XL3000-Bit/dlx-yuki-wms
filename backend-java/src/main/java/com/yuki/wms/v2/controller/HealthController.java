package com.yuki.wms.v2.controller;

import com.yuki.wms.v2.mapper.ReportingReadMapper;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController("v2HealthController")
@RequestMapping("/api/v2/health")
public class HealthController {
    private final ReportingReadMapper mapper;

    public HealthController(ReportingReadMapper mapper) { this.mapper = mapper; }

    @GetMapping
    public Map<String, String> health() {
        return Map.of("status", "ok", "service", "yuki-wms-java", "mode", "read-only");
    }

    @GetMapping("/db")
    public Map<String, String> database() {
        mapper.ping();
        return Map.of("status", "ok", "database", "reachable", "mode", "read-only");
    }
}

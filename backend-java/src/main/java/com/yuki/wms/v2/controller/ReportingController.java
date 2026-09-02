package com.yuki.wms.v2.controller;

import com.dlxyuki.wms.user.UserAccount;
import com.yuki.wms.v2.service.DashboardReadService;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController("v2ReportingController")
@RequestMapping("/api/v2/reporting")
public class ReportingController {
    private final DashboardReadService service;

    public ReportingController(DashboardReadService service) { this.service = service; }

    @GetMapping("/dashboard")
    public Map<String, Object> dashboard(@AuthenticationPrincipal UserAccount user) {
        return service.dashboard(user);
    }
}

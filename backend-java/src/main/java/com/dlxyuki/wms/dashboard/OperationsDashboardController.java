package com.dlxyuki.wms.dashboard;

import com.dlxyuki.wms.user.UserAccount;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/dashboard")
public class OperationsDashboardController {
    private final OperationsDashboardService service;

    public OperationsDashboardController(OperationsDashboardService service) { this.service = service; }

    @GetMapping("/operations")
    Map<String, Object> operations(
        @RequestParam(name = "date_from", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateFrom,
        @RequestParam(name = "date_to", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateTo,
        @RequestParam(name = "warehouse_id", required = false) Long warehouseId,
        @AuthenticationPrincipal UserAccount user) {
        return service.operations(dateFrom, dateTo, warehouseId, user);
    }
}

package com.dlxyuki.wms.load;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/loads")
public class LoadController {
    private final LoadService service;
    public LoadController(LoadService service) { this.service = service; }

    @GetMapping
    Object list(@RequestParam(defaultValue = "1") @Min(1) int page,
                @RequestParam(name = "per_page", defaultValue = "20") @Min(1) @Max(100) int perPage,
                @RequestParam(required = false) String q,
                @RequestParam(required = false) @Pattern(regexp = "PLANNED|READY|DISPATCHED|COMPLETED|CANCELED") String status,
                @RequestParam(name = "warehouse_id", required = false) Long warehouseId,
                @RequestParam(name = "appointment_from", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate appointmentFrom,
                @RequestParam(name = "appointment_to", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate appointmentTo,
                @AuthenticationPrincipal UserAccount user) {
        return service.list(page, perPage, q, status, warehouseId, appointmentFrom, appointmentTo, user);
    }

    @GetMapping("/{load_id}")
    Map<String,Object> detail(@PathVariable("load_id") long id, @AuthenticationPrincipal UserAccount user) {
        return service.detail(id, user);
    }

    @GetMapping("/{load_id}/execution-summary")
    Map<String,Object> executionSummary(@PathVariable("load_id") long id, @AuthenticationPrincipal UserAccount user) {
        return service.executionSummary(id, user);
    }
}

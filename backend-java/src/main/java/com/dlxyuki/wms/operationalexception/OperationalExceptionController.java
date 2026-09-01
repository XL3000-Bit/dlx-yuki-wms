package com.dlxyuki.wms.operationalexception;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import java.time.OffsetDateTime;
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
@RequestMapping("/api/v1/operational-exceptions")
public class OperationalExceptionController {
    private final OperationalExceptionService service;
    public OperationalExceptionController(OperationalExceptionService service) { this.service=service; }

    @GetMapping
    Object list(@RequestParam(defaultValue="1") @Min(1) int page,
                @RequestParam(name="per_page",defaultValue="20") @Min(1) @Max(100) int perPage,
                @RequestParam(required=false) String q,
                @RequestParam(required=false) @Pattern(regexp="OPEN|INVESTIGATING|RESOLVED|CANCELED") String status,
                @RequestParam(required=false) @Pattern(regexp="LOW|MEDIUM|HIGH|CRITICAL") String severity,
                @RequestParam(name="exception_type",required=false) @Pattern(regexp="INVENTORY|PICKING|OUTBOUND|CONTAINER|DOCUMENT|APPOINTMENT|WAREHOUSE|DATA|OTHER") String type,
                @RequestParam(name="warehouse_id",required=false) Long warehouseId,
                @RequestParam(name="assigned_to",required=false) Long assignedTo,
                @RequestParam(name="reported_from",required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE_TIME) OffsetDateTime reportedFrom,
                @RequestParam(name="reported_to",required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE_TIME) OffsetDateTime reportedTo,
                @AuthenticationPrincipal UserAccount user) {
        return service.list(page,perPage,q,status,severity,type,warehouseId,assignedTo,reportedFrom,reportedTo,user);
    }

    @GetMapping("/{exception_id}")
    Map<String,Object> detail(@PathVariable("exception_id") long id,@AuthenticationPrincipal UserAccount user) { return service.detail(id,user); }

    @GetMapping("/{exception_id}/events")
    Map<String,Object> events(@PathVariable("exception_id") long id,
                              @RequestParam(defaultValue="desc") @Pattern(regexp="asc|desc") String order,
                              @RequestParam(defaultValue="50") @Min(1) @Max(100) int limit,
                              @RequestParam(defaultValue="0") @Min(0) int offset,
                              @AuthenticationPrincipal UserAccount user) { return service.events(id,order,limit,offset,user); }
}

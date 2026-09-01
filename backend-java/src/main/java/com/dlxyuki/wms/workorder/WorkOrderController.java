package com.dlxyuki.wms.workorder;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/work-orders")
public class WorkOrderController {
    private final WorkOrderService service;
    public WorkOrderController(WorkOrderService service) { this.service = service; }

    @GetMapping
    Object list(@RequestParam(defaultValue="1") @Min(1) int page,
                @RequestParam(name="per_page",defaultValue="20") @Min(1) @Max(100) int perPage,
                @RequestParam(required=false) String q,
                @RequestParam(required=false) @Pattern(regexp="OPEN|ASSIGNED|IN_PROGRESS|COMPLETED|CANCELED") String status,
                @RequestParam(name="work_order_type",required=false) @Pattern(regexp="PICK|STAGE|LOAD|CHECK|GENERAL") String workOrderType,
                @RequestParam(name="warehouse_id",required=false) Long warehouseId,
                @RequestParam(required=false) @Pattern(regexp="LOW|NORMAL|HIGH|URGENT") String priority,
                @RequestParam(name="assigned_to",required=false) Long assignedTo,
                @AuthenticationPrincipal UserAccount user) {
        return service.list(page,perPage,q,status,workOrderType,warehouseId,priority,assignedTo,user);
    }

    @GetMapping("/{work_order_id}")
    Map<String,Object> detail(@PathVariable("work_order_id") long id,@AuthenticationPrincipal UserAccount user) {
        return service.detail(id,user);
    }

    @GetMapping("/{work_order_id}/events")
    Map<String,Object> events(@PathVariable("work_order_id") long id,
                              @RequestParam(defaultValue="desc") @Pattern(regexp="asc|desc") String order,
                              @RequestParam(defaultValue="50") @Min(1) @Max(100) int limit,
                              @RequestParam(defaultValue="0") @Min(0) int offset,
                              @AuthenticationPrincipal UserAccount user) {
        return service.events(id,order,limit,offset,user);
    }
}

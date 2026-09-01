package com.dlxyuki.wms.outbound;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@Validated @RestController @RequestMapping("/api/v1/outbounds")
public class OutboundController {
 private final OutboundService service; public OutboundController(OutboundService service){this.service=service;}
 @GetMapping Object list(@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(name="per_page",defaultValue="20") @Min(1) @Max(100) int perPage,
  @RequestParam(required=false) String q,@RequestParam(name="ob_no",required=false) String obNo,@RequestParam(required=false) Integer status,
  @RequestParam(name="ob_type",required=false) String obType,@RequestParam(name="customer_id",required=false) Long customerId,
  @RequestParam(name="warehouse_id",required=false) Long warehouseId,@RequestParam(name="carrier_id",required=false) Long carrierId,
  @RequestParam(name="fba_shipment_id",required=false) Long fbaShipmentId,@RequestParam(name="fc_code",required=false) String fcCode,
  @RequestParam(name="del_code",required=false) String delCode,@RequestParam(name="agent_code",required=false) String agentCode,
  @RequestParam(name="sort_by",defaultValue="id") String sortBy,@RequestParam(name="sort_order",defaultValue="desc") @Pattern(regexp="asc|desc") String sortOrder,
  @AuthenticationPrincipal UserAccount user){return service.list(new OutboundQuery(page,perPage,q,obNo,status,obType,customerId,warehouseId,carrierId,fbaShipmentId,fcCode,delCode,agentCode,sortBy,sortOrder),user);}
 @GetMapping("/workbench") Object workbench(@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(name="per_page",defaultValue="20") @Min(1) @Max(100) int perPage,
  @RequestParam(required=false) String q,@RequestParam(required=false) Integer status,@RequestParam(name="ob_type",required=false) String obType,
  @RequestParam(name="warehouse_id",required=false) Long warehouseId,@RequestParam(name="carrier_id",required=false) Long carrierId,
  @RequestParam(name="sort_by",defaultValue="created_at") String sortBy,@RequestParam(name="sort_order",defaultValue="desc") @Pattern(regexp="asc|desc") String sortOrder,
  @AuthenticationPrincipal UserAccount user){return service.workbench(new WorkbenchQuery(page,perPage,q,status,obType,warehouseId,carrierId,sortBy,sortOrder),user);}
 @GetMapping("/{id}/workbench-detail") Object workbenchDetail(@PathVariable long id,@AuthenticationPrincipal UserAccount user){return service.workbenchDetail(id,user);}
 @GetMapping("/{ob_id}/dispatch-readiness") Object readiness(@PathVariable(name="ob_id") long id,@AuthenticationPrincipal UserAccount user){return service.readiness(id,user);}
 @GetMapping("/{ob_id}/allocations") Object allocations(@PathVariable(name="ob_id") long id,@AuthenticationPrincipal UserAccount user){return service.allocations(id,user);}
 @GetMapping("/{ob_id}") Object get(@PathVariable(name="ob_id") long id,@AuthenticationPrincipal UserAccount user){return service.get(id,user);}
}

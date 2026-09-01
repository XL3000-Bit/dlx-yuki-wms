package com.dlxyuki.wms.master;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.*;
import java.util.*;
import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/v1/master-data")
public class MasterDataController {
    private final MasterDataRepository data;
    public MasterDataController(MasterDataRepository data){this.data=data;}
    @GetMapping("/customers") List<Map<String,Object>> customers(@AuthenticationPrincipal UserAccount u){return data.customers(u);}
    @GetMapping("/warehouses") List<Map<String,Object>> warehouses(@AuthenticationPrincipal UserAccount u){return data.warehouses(u);}
    @GetMapping("/warehouse-areas") List<Map<String,Object>> areas(@AuthenticationPrincipal UserAccount u){return data.areas(u);}
    @GetMapping("/warehouse-locations") List<Map<String,Object>> locations(@AuthenticationPrincipal UserAccount u,@RequestParam(name="location_code",required=false) String locationCode){return data.locations(u,locationCode);}
    @GetMapping("/carriers") List<Map<String,Object>> carriers(){return data.carriers();}
    @GetMapping("/amazon-fc-addresses") List<Map<String,Object>> fcs(){return data.fcs();}
    @GetMapping("/amazon-fc-addresses/{code}") Map<String,Object> fc(@PathVariable String code){return data.fc(code).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"Amazon FC not found"));}
    @PostMapping("/{kind}") @ResponseStatus(HttpStatus.CREATED) Map<String,Object> create(@PathVariable String kind,@RequestBody Map<String,Object> body,@AuthenticationPrincipal UserAccount u){UserManagementService.admin(u);try{return data.create(kind,body);}catch(IllegalArgumentException e){throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY,"Missing or invalid field: "+e.getMessage());}}
}

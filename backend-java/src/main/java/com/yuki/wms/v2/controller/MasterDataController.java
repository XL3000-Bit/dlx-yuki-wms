package com.yuki.wms.v2.controller;

import com.dlxyuki.wms.user.UserAccount;
import com.yuki.wms.v2.service.MasterDataReadService;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController("v2MasterDataController")
@RequestMapping("/api/v2")
public class MasterDataController {
    private final MasterDataReadService service;

    public MasterDataController(MasterDataReadService service) { this.service = service; }

    @GetMapping("/customers")
    public List<Map<String, Object>> customers(@AuthenticationPrincipal UserAccount user) {
        return service.customers(user);
    }

    @GetMapping("/warehouses")
    public List<Map<String, Object>> warehouses(@AuthenticationPrincipal UserAccount user) {
        return service.warehouses(user);
    }

    @GetMapping("/carriers")
    public List<Map<String, Object>> carriers() { return service.carriers(); }

    @GetMapping("/fc-addresses")
    public List<Map<String, Object>> fcAddresses() { return service.fcAddresses(); }
}

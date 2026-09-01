package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.user.UserAccount;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/fba")
class FbaAllocationController {
    private final FbaService service;

    FbaAllocationController(FbaService service) {
        this.service = service;
    }

    @GetMapping("/{fba_id}/allocations")
    Object allocations(@PathVariable("fba_id") long fbaId, @AuthenticationPrincipal UserAccount user) {
        return service.allocations(fbaId, user);
    }
}

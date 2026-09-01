package com.dlxyuki.wms.user;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/users")
public class UserController {
    private final UserManagementService service;
    public UserController(UserManagementService service){this.service=service;}
    @GetMapping("/me") UserResponse me(@AuthenticationPrincipal UserAccount user) { return UserResponse.from(user); }
    @PostMapping("/bootstrap") @ResponseStatus(HttpStatus.CREATED) UserResponse bootstrap(@Valid @RequestBody UserRequests.Create payload){return service.bootstrap(payload);}
    @GetMapping List<UserResponse> list(@AuthenticationPrincipal UserAccount user){return service.list(user);}
    @PostMapping @ResponseStatus(HttpStatus.CREATED) UserResponse create(@Valid @RequestBody UserRequests.Create payload,@AuthenticationPrincipal UserAccount user){return service.create(payload,user);}
    @PatchMapping("/{id}") UserResponse update(@PathVariable long id,@Valid @RequestBody UserRequests.Update payload,@AuthenticationPrincipal UserAccount user){return service.update(id,payload,user);}
    @PatchMapping("/{id}/scope") UserResponse scope(@PathVariable long id,@RequestBody UserRequests.Scope payload,@AuthenticationPrincipal UserAccount user){return service.scope(id,payload,user);}
}

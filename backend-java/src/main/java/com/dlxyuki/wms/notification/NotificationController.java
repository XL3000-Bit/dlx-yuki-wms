package com.dlxyuki.wms.notification;

import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/notifications")
public class NotificationController {
    private final NotificationService service;
    public NotificationController(NotificationService service) { this.service = service; }

    @GetMapping("/unread-count")
    Object unreadCount(@AuthenticationPrincipal UserAccount user) { return service.unreadCount(user); }

    @GetMapping
    Object list(@RequestParam(defaultValue="1") @Min(1) int page,
                @RequestParam(name="per_page", defaultValue="20") @Min(1) @Max(100) int perPage,
                @RequestParam(name="unread_only", defaultValue="false") boolean unreadOnly,
                @AuthenticationPrincipal UserAccount user) {
        return service.list(page, perPage, unreadOnly, user);
    }
}

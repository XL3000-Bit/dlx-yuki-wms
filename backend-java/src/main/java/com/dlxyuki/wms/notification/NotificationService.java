package com.dlxyuki.wms.notification;

import com.dlxyuki.wms.user.UserAccount;
import org.springframework.stereotype.Service;

@Service
class NotificationService {
    private final NotificationRepository repository;
    NotificationService(NotificationRepository repository) { this.repository = repository; }
    Object list(int page, int perPage, boolean unreadOnly, UserAccount user) { return repository.list(page, perPage, unreadOnly, user); }
    Object unreadCount(UserAccount user) { return repository.unreadCount(user); }
}

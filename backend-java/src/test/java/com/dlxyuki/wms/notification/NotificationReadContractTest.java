package com.dlxyuki.wms.notification;

import static org.assertj.core.api.Assertions.assertThat;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

class NotificationReadContractTest {
    @Test void exposesOnlyTheTwoReadRoutes() {
        assertThat(NotificationController.class.getAnnotation(RequestMapping.class).value()).containsExactly("/api/v1/notifications");
        var methods = Arrays.stream(NotificationController.class.getDeclaredMethods()).toList();
        assertThat(methods.stream().filter(m -> m.isAnnotationPresent(GetMapping.class)).map(m -> Arrays.asList(m.getAnnotation(GetMapping.class).value())))
            .containsExactlyInAnyOrder(java.util.List.of(), java.util.List.of("/unread-count"));
        assertThat(methods.stream().filter(m -> m.isAnnotationPresent(PostMapping.class))).isEmpty();
    }
}

package com.dlxyuki.wms.search;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/search")
public class SearchController {
    private final SearchService service;
    public SearchController(SearchService service) { this.service = service; }

    @GetMapping
    Map<String,Object> search(@RequestParam String q,
                              @RequestParam(defaultValue="20") @Min(1) @Max(50) int limit,
                              @AuthenticationPrincipal UserAccount user) {
        String query = q == null ? "" : q.trim();
        if (query.length() < 2) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY,
            "Search query must contain at least 2 characters");
        return service.search(query, limit, user);
    }
}

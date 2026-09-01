package com.dlxyuki.wms.companyprofile;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.util.Map;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/company-profile")
public class CompanyProfileController {
    private final CompanyProfileRepository repository;
    CompanyProfileController(CompanyProfileRepository repository) { this.repository = repository; }

    @GetMapping
    Map<String,Object> read(@AuthenticationPrincipal UserAccount user) {
        try {
            return repository.first().orElseThrow(() -> new ApiException(HttpStatus.SERVICE_UNAVAILABLE,
                "Company profile is not initialized"));
        } catch (DataAccessException error) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,
                "Company profile table is missing. Run alembic upgrade head.");
        }
    }
}

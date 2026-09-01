package com.dlxyuki.wms.load;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
class LoadService {
    private final LoadRepository repository;
    LoadService(LoadRepository repository) { this.repository = repository; }
    Object list(int page, int perPage, String q, String status, Long warehouseId, LocalDate from, LocalDate to, UserAccount user) {
        return repository.list(page, perPage, q, status, warehouseId, from, to, user);
    }
    Map<String,Object> detail(long id, UserAccount user) {
        return repository.find(id, user).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Load not found"));
    }
    Map<String,Object> executionSummary(long id, UserAccount user) {
        detail(id, user);
        return repository.executionSummary(id);
    }
}

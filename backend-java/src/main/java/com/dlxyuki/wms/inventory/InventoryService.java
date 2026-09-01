package com.dlxyuki.wms.inventory;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final InventoryRepository repository;
    public InventoryService(InventoryRepository repository) { this.repository = repository; }

    public InventoryListResponse list(InventoryQuery query, UserAccount user) {
        return repository.list(query, user);
    }

    public InventoryResponse get(long id, UserAccount user) {
        return repository.find(id, user)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Inventory lot not found"));
    }

    public List<InventoryTransactionResponse> transactions(long id, UserAccount user) {
        get(id, user);
        return repository.transactions(id);
    }
}

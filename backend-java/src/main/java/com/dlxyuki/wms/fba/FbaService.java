package com.dlxyuki.wms.fba;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class FbaService {
    private final FbaRepository repository;
    public FbaService(FbaRepository repository) { this.repository=repository; }
    Object list(FbaQuery q, UserAccount u) { return repository.list(q,u); }
    Object workbench(WorkbenchQuery q, UserAccount u) { return repository.workbench(q,u); }
    Object workbenchDetail(long id, UserAccount u) { return repository.workbenchDetail(id,u)
        .orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"FBA shipment not found")); }
    Object get(long id, UserAccount u) { return repository.find(id,u).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"FBA shipment not found")); }
    Object allocations(long id, UserAccount u) { return repository.findAllocations(id,u)
        .orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"FBA shipment not found")); }
}

package com.dlxyuki.wms.document;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
class OperationalDocumentService {
    private final OperationalDocumentRepository repository;
    OperationalDocumentService(OperationalDocumentRepository repository) { this.repository=repository; }
    Object list(String q,String type,String status,Long warehouseId,Long customerId,Long loadId,Long outboundId,Long bolId,Long workOrderId,Long exceptionId,int page,int perPage,UserAccount user) {
        return repository.list(q,type,status,warehouseId,customerId,loadId,outboundId,bolId,workOrderId,exceptionId,page,perPage,user);
    }
    Object detail(long id,UserAccount user) { return repository.find(id,user).orElseThrow(()->notFound()); }
    Object events(long id,UserAccount user) { repository.find(id,user).orElseThrow(()->notFound()); return repository.events(id); }
    private static ApiException notFound() { return new ApiException(HttpStatus.NOT_FOUND,"Document not found"); }
}

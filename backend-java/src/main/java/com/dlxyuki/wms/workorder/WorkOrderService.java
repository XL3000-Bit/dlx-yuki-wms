package com.dlxyuki.wms.workorder;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
class WorkOrderService {
    private final WorkOrderRepository repository;
    WorkOrderService(WorkOrderRepository repository) { this.repository=repository; }
    Object list(int page,int perPage,String q,String status,String type,Long warehouseId,String priority,Long assignedTo,UserAccount user) {
        return repository.list(page,perPage,q,status,type,warehouseId,priority,assignedTo,user);
    }
    Map<String,Object> detail(long id,UserAccount user) {
        return repository.find(id,user).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"Work order not found"));
    }
    Map<String,Object> events(long id,String order,int limit,int offset,UserAccount user) {
        detail(id,user); return repository.events(id,order,limit,offset);
    }
}

package com.dlxyuki.wms.operationalexception;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.UserAccount;
import java.time.OffsetDateTime;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
class OperationalExceptionService {
    private final OperationalExceptionRepository repository;
    OperationalExceptionService(OperationalExceptionRepository repository) { this.repository=repository; }
    Object list(int page,int size,String q,String status,String severity,String type,Long warehouseId,Long assignedTo,OffsetDateTime from,OffsetDateTime to,UserAccount user) {
        return repository.list(page,size,q,status,severity,type,warehouseId,assignedTo,from,to,user);
    }
    Map<String,Object> detail(long id,UserAccount user) { return repository.find(id,user).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"Operational exception not found")); }
    Map<String,Object> events(long id,String order,int limit,int offset,UserAccount user) { detail(id,user);return repository.events(id,order,limit,offset); }
}

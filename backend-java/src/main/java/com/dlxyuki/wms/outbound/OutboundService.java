package com.dlxyuki.wms.outbound;
import com.dlxyuki.wms.config.ApiException; import com.dlxyuki.wms.user.UserAccount; import org.springframework.http.HttpStatus; import org.springframework.stereotype.Service;
@Service public class OutboundService {private final OutboundRepository repo; public OutboundService(OutboundRepository r){repo=r;}
 Object list(OutboundQuery q,UserAccount u){return repo.list(q,u);} Object workbench(WorkbenchQuery q,UserAccount u){return repo.workbench(q,u);}
 Object get(long id,UserAccount u){return repo.find(id,u).orElseThrow(()->missing());} Object allocations(long id,UserAccount u){ensure(id,u);return repo.allocations(id);}
 Object readiness(long id,UserAccount u){ensure(id,u);return repo.readiness(id);} Object workbenchDetail(long id,UserAccount u){ensure(id,u);return repo.workbenchDetail(id,u);}
 private void ensure(long id,UserAccount u){if(repo.find(id,u).isEmpty())throw missing();} private ApiException missing(){return new ApiException(HttpStatus.NOT_FOUND,"Outbound order not found");}}

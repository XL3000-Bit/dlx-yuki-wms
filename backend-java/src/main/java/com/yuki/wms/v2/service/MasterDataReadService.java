package com.yuki.wms.v2.service;

import com.dlxyuki.wms.user.UserAccount;
import com.yuki.wms.v2.mapper.ReportingReadMapper;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class MasterDataReadService {
    private final ReportingReadMapper mapper;

    public MasterDataReadService(ReportingReadMapper mapper) { this.mapper = mapper; }

    public List<Map<String, Object>> customers(UserAccount user) {
        ReadScope scope = ReadScope.from(user);
        return mapper.findCustomers(scope.allCustomers(), scope.customerIds());
    }

    public List<Map<String, Object>> warehouses(UserAccount user) {
        ReadScope scope = ReadScope.from(user);
        return mapper.findWarehouses(scope.allWarehouses(), scope.warehouseIds());
    }

    public List<Map<String, Object>> carriers() { return mapper.findCarriers(); }
    public List<Map<String, Object>> fcAddresses() { return mapper.findFcAddresses(); }
}

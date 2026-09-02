package com.yuki.wms.v2.service;

import com.dlxyuki.wms.user.UserAccount;
import com.yuki.wms.v2.mapper.ReportingReadMapper;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class DashboardReadService {
    private final ReportingReadMapper mapper;

    public DashboardReadService(ReportingReadMapper mapper) { this.mapper = mapper; }

    public Map<String, Object> dashboard(UserAccount user) {
        ReadScope s = ReadScope.from(user);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("inbound", mapper.inboundSummary(s.allWarehouses(), s.warehouseIds(), s.allCustomers(), s.customerIds()));
        result.put("inventory", mapper.inventorySummary(s.allWarehouses(), s.warehouseIds(), s.allCustomers(), s.customerIds()));
        result.put("outbound", mapper.outboundSummary(s.allWarehouses(), s.warehouseIds(), s.allCustomers(), s.customerIds()));
        result.put("generated_at", Instant.now());
        return result;
    }
}

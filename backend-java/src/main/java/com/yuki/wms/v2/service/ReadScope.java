package com.yuki.wms.v2.service;

import com.dlxyuki.wms.user.UserAccount;
import java.util.List;

record ReadScope(boolean allWarehouses, List<Long> warehouseIds,
                 boolean allCustomers, List<Long> customerIds) {
    static ReadScope from(UserAccount user) {
        boolean admin = "ADMIN".equals(user.role());
        return new ReadScope(admin || "ALL".equals(user.warehouseScopeMode()), user.warehouseIds(),
            admin || "ALL".equals(user.customerScopeMode()), user.customerIds());
    }
}

package com.yuki.wms.v2.mapper;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface ReportingReadMapper {
    int ping();
    List<Map<String, Object>> findCustomers(@Param("allCustomers") boolean allCustomers,
                                            @Param("customerIds") List<Long> customerIds);
    List<Map<String, Object>> findWarehouses(@Param("allWarehouses") boolean allWarehouses,
                                             @Param("warehouseIds") List<Long> warehouseIds);
    List<Map<String, Object>> findCarriers();
    List<Map<String, Object>> findFcAddresses();
    Map<String, Object> inboundSummary(@Param("allWarehouses") boolean allWarehouses,
                                       @Param("warehouseIds") List<Long> warehouseIds,
                                       @Param("allCustomers") boolean allCustomers,
                                       @Param("customerIds") List<Long> customerIds);
    Map<String, Object> inventorySummary(@Param("allWarehouses") boolean allWarehouses,
                                         @Param("warehouseIds") List<Long> warehouseIds,
                                         @Param("allCustomers") boolean allCustomers,
                                         @Param("customerIds") List<Long> customerIds);
    Map<String, Object> outboundSummary(@Param("allWarehouses") boolean allWarehouses,
                                        @Param("warehouseIds") List<Long> warehouseIds,
                                        @Param("allCustomers") boolean allCustomers,
                                        @Param("customerIds") List<Long> customerIds);
}

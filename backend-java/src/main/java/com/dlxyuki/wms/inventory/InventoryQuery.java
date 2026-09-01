package com.dlxyuki.wms.inventory;

import java.time.LocalDate;

public record InventoryQuery(
    int page, int perPage, String q, String containerNumber, String fcCode,
    Long customerId, Long warehouseId, Long locationId, Integer status,
    String priorityLevel, LocalDate inboundDateFrom, LocalDate inboundDateTo,
    Integer agingMin, Integer agingMax, Boolean hasAvailable,
    String sortBy, String sortOrder
) {}

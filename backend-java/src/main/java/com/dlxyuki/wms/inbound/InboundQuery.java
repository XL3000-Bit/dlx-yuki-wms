package com.dlxyuki.wms.inbound;

import java.time.LocalDate;

public record InboundQuery(
    int page, int perPage, String q, String containerNumber, Long customerId, Long warehouseId,
    String fcCode, Long locationId, Integer status, LocalDate unloadDateFrom, LocalDate unloadDateTo,
    LocalDate receivedDateFrom, LocalDate receivedDateTo, String sortBy, String sortOrder
) {}

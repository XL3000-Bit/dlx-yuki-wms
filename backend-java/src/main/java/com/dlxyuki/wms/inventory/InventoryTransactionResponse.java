package com.dlxyuki.wms.inventory;

import java.time.OffsetDateTime;
import java.util.Map;

public record InventoryTransactionResponse(
    long id,
    String transactionType,
    String palletDelta,
    String cartonDelta,
    String weightDelta,
    String cbmDelta,
    InventoryResponse.NamedRef fromLocation,
    InventoryResponse.NamedRef toLocation,
    String referenceType,
    Long referenceId,
    Map<String,Object> beforeSnapshot,
    Map<String,Object> afterSnapshot,
    String remark,
    CreatedBy createdBy,
    OffsetDateTime createdAt
) {
    public record CreatedBy(long id, String displayName) {}
}

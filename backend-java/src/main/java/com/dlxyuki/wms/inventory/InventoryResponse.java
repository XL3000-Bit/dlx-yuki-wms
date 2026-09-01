package com.dlxyuki.wms.inventory;

import java.time.LocalDate;
import java.time.OffsetDateTime;

public record InventoryResponse(
    long id,
    String lotNo,
    String containerNumber,
    String fcCode,
    String marking,
    NamedRef customer,
    NamedRef warehouse,
    NamedRef location,
    long sourceInboundId,
    LocalDate inboundDate,
    Integer agingDays,
    String priorityLevel,
    String priorityLabel,
    String originalPalletQty,
    String availablePalletQty,
    String allocatedPalletQty,
    String holdPalletQty,
    String originalCartonQty,
    String availableCartonQty,
    String allocatedCartonQty,
    String holdCartonQty,
    String originalWeightLbs,
    String availableWeightLbs,
    String allocatedWeightLbs,
    String originalCbm,
    String availableCbm,
    String allocatedCbm,
    int status,
    String statusName,
    String remark,
    OffsetDateTime createdAt,
    OffsetDateTime updatedAt
) {
    public record NamedRef(long id, String code, String name) {}
}

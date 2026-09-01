package com.dlxyuki.wms.inbound;

import java.time.LocalDate;
import java.time.OffsetDateTime;

public record InboundResponse(
    long id,
    String inboundNo,
    String containerNumber,
    NamedRef customer,
    NamedRef warehouse,
    NamedRef location,
    LocalDate unloadDate,
    LocalDate receivedDate,
    String fcCode,
    String marking,
    String palletQty,
    String cartonQty,
    String weightLbs,
    String cbm,
    int status,
    String statusName,
    Integer agingDays,
    String remark,
    UserRef createdBy,
    OffsetDateTime createdAt,
    OffsetDateTime updatedAt,
    boolean inventoryCreated,
    Long inventoryLotId
) {
    public record NamedRef(long id, String code, String name) {}
    public record UserRef(long id, String displayName) {}
}

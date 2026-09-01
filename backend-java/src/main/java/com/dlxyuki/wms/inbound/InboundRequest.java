package com.dlxyuki.wms.inbound;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;

public record InboundRequest(
    @NotNull @Size(min = 1, max = 50) String containerNumber,
    Long customerId,
    @NotNull Long warehouseId,
    LocalDate unloadDate,
    LocalDate receivedDate,
    @Size(max = 20) String fcCode,
    @Size(max = 100) String marking,
    @DecimalMin("0") BigDecimal palletQty,
    @DecimalMin("0") BigDecimal cartonQty,
    @DecimalMin("0") BigDecimal weightLbs,
    @DecimalMin("0") BigDecimal cbm,
    Long locationId,
    @Min(0) @Max(5) Integer status,
    String remark
) {
    public BigDecimal effectivePalletQty() { return palletQty == null ? BigDecimal.ZERO : palletQty; }
    public BigDecimal effectiveCartonQty() { return cartonQty == null ? BigDecimal.ZERO : cartonQty; }
    public int effectiveStatus() { return status == null ? 0 : status; }
}

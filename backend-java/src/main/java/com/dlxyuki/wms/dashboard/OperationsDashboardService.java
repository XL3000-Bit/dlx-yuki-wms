package com.dlxyuki.wms.dashboard;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.config.AppProperties;
import com.dlxyuki.wms.user.UserAccount;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class OperationsDashboardService {
    private final OperationsDashboardRepository repository;
    private final ZoneId businessZone;

    public OperationsDashboardService(OperationsDashboardRepository repository, AppProperties properties) {
        this.repository = repository;
        this.businessZone = ZoneId.of(properties.businessTimezone());
    }

    public Map<String, Object> operations(LocalDate dateFrom, LocalDate dateTo, Long warehouseId, UserAccount user) {
        ZonedDateTime now = ZonedDateTime.now(businessZone);
        LocalDate startDate = dateFrom == null ? now.toLocalDate() : dateFrom;
        LocalDate endDate = dateTo == null ? startDate : dateTo;
        if (endDate.isBefore(startDate)) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "date_to must be on or after date_from");
        if (ChronoUnit.DAYS.between(startDate, endDate) > 366) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Dashboard range cannot exceed 367 days");
        assertWarehouseAccess(user, warehouseId);
        OffsetDateTime start = startDate.atStartOfDay(businessZone).toOffsetDateTime();
        OffsetDateTime end = endDate.plusDays(1).atStartOfDay(businessZone).toOffsetDateTime();
        return repository.build(user, start, end, now.toOffsetDateTime(), warehouseId);
    }

    private void assertWarehouseAccess(UserAccount user, Long warehouseId) {
        if (warehouseId == null || "ADMIN".equalsIgnoreCase(user.role()) || "ALL".equalsIgnoreCase(user.warehouseScopeMode())) return;
        if (!user.warehouseIds().contains(warehouseId)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Warehouse is outside your assigned scope");
        }
    }
}

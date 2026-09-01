package com.dlxyuki.wms.inventory;

import java.util.List;

public record InventoryListResponse(List<InventoryResponse> data, PaginationMeta meta) {
    public record PaginationMeta(int page, int perPage, long total, long totalPages) {}
}

package com.dlxyuki.wms.inbound;

import java.util.List;

public record InboundListResponse(List<InboundResponse> data, PaginationMeta meta) {
    public record PaginationMeta(int page, int perPage, long total, long totalPages) {}
}

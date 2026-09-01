package com.dlxyuki.wms.imports;

import java.time.OffsetDateTime;
import java.util.Map;

public record ImportJobResponse(
    long id, String module, String fileName, String originalFileName, String status,
    long totalRows, long processedRows, double progressPercent, String currentStage,
    long validRows, long warningRows, long errorRows, long importedRows,
    long createdBy, OffsetDateTime createdAt, OffsetDateTime completedAt,
    Map<String,Object> mapping, String profileCode, String sourceSheet, String fileHash,
    Map<String,Object> performance, Map<String,Object> reconciliation, String statusName
) { }

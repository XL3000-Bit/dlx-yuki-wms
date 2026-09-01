package com.dlxyuki.wms.containertracking;
import java.time.LocalDate;
record ContainerTrackingQuery(int page,int perPage,String q,String status,Long warehouseId,String outboundWindow,LocalDate outboundFrom,LocalDate outboundTo,String dispatchPriority,String sortBy,String sortOrder){}

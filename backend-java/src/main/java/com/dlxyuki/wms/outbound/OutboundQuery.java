package com.dlxyuki.wms.outbound;

record OutboundQuery(int page,int perPage,String q,String obNo,Integer status,String obType,Long customerId,
 Long warehouseId,Long carrierId,Long fbaShipmentId,String fcCode,String delCode,String agentCode,String sortBy,String sortOrder) {}

package com.dlxyuki.wms.outbound;

record WorkbenchQuery(int page,int perPage,String q,Integer status,String obType,Long warehouseId,Long carrierId,String sortBy,String sortOrder) {}

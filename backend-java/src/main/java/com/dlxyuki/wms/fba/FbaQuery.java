package com.dlxyuki.wms.fba;
record FbaQuery(int page,int perPage,String q,String fbaNo,Long customerId,Long warehouseId,String amazonFcCode,Long carrierId,Integer status,String containerNumber,Long locationId,String priorityLevel,Integer agingMin,Integer agingMax,String appointmentFrom,String appointmentTo,String sortBy,String sortOrder) {}

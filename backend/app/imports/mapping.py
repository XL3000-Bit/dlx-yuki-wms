ALIASES={
"container_number":["container","container no","container number","cntr","cntr#","柜号","箱号"],"customer":["customer","customer name","customer code","客户"],"warehouse":["warehouse","warehouse code","warehouse name","仓库"],"fc_code":["fc","fc code","amazon fc","destination","仓点"],"pallet_qty":["pallet","pallet qty","plt","plts","板数"],"carton_qty":["carton","cartons","ctn","ctns","carton qty","箱数"],"weight_lbs":["weight","weight lbs","weight(lbs)","lbs","lb","重量"],"cbm":["cbm","cubic meter","volume","方数"],"location":["location","loc","warehouse location","库位"],"received_date":["received date","inbound date","receive date","入库日期"],"unload_date":["unload date","unloading date","拆柜日期","卸柜日期"],"marking":["marking","mark","唛头"],"remark":["remark","remarks","note","notes","备注"]}
def normalize(value:str)->str:return " ".join(value.strip().lower().replace("_"," ").split())
def suggest_mapping(headers:list[str])->dict[str,str]:
    lookup={normalize(alias):field for field,aliases in ALIASES.items() for alias in aliases};return {header:lookup.get(normalize(header),"") for header in headers}
def validate_mapping(mapping:dict[str,str])->None:
    targets=[v for v in mapping.values() if v]
    if len(targets)!=len(set(targets)):raise ValueError("A system field cannot be mapped more than once")
    if "container_number" not in targets or "warehouse" not in targets:raise ValueError("Container Number and Warehouse mappings are required")

FBA_ALIASES={"fba_no":["fba","fba no","fba number"],"shipment_id":["shipment","shipment id","amazon shipment id"],"customer":["customer","customer name","customer code"],"warehouse":["warehouse","warehouse code","warehouse name"],"amazon_fc_code":["fc","fc code","amazon fc","destination","amazon code"],"container_number":["container","container no","container number","cntr","cntr#"],"pallet_qty":["pallet","pallet qty","plt","plts"],"carton_qty":["carton","cartons","ctn","ctns","carton qty"],"weight_lbs":["weight","weight lbs","weight(lbs)","lbs","lb"],"cbm":["cbm","cubic meter","volume"],"scheduled_pickup_at":["scheduled pickup","schedule pu","pickup date"],"appointment_time":["apt","apt time","appointment","appointment time"],"carrier":["carrier","carrier code","carrier name"],"st_number":["st","st number","st#"],"reference_no":["reference","reference no","ref","ref#"],"remark":["remark","remarks","notes"]}
def suggest_fba_mapping(headers:list[str])->dict[str,str]:
    lookup={normalize(alias):field for field,aliases in FBA_ALIASES.items()for alias in aliases};return{header:lookup.get(normalize(header),"")for header in headers}
def validate_fba_mapping(mapping:dict[str,str])->None:
    targets=[v for v in mapping.values()if v]
    if len(targets)!=len(set(targets)):raise ValueError("A system field cannot be mapped more than once")
    for required in("warehouse","amazon_fc_code","container_number"):
        if required not in targets:raise ValueError(f"{required} mapping is required")
OUTBOUND_ALIASES={"ob_no":["ob","ob#","ob no","ob number","outbound no","outbound number"],"ob_type":["type","ob type","outbound type"],"customer":["customer","customer code","customer name","client"],"warehouse":["warehouse","warehouse code","whs"],"carrier":["carrier","carrier code","scac","trucking"],"fba_no":["fba","fba no","fba number"],"lot_no":["lot","lot no","lot number","inventory lot"],"container_number":["container","container no","container number","cntr","cntr#"],"fc_code":["fc","fc code","amazon fc","destination"],"marking":["marking","mark"],"pallet_qty":["pallet","pallet qty","plt","plts"],"carton_qty":["carton","carton qty","ctn","ctns"],"weight_lbs":["weight","weight lbs","weight(lbs)","lb","lbs"],"cbm":["cbm","volume","cubic meter"],"loading_team":["loading team"],"truck_type":["truck type"],"notify_carrier":["notify carrier"],"delivery_type":["delivery type"],"pickup_location":["pickup location"],"schedule_pickup_at":["schedule pu","schedule pickup","pickup time","pu time","outbound date","ship date","scheduled outbound","出库日期","最早出库时间"],"delivery_appointment_time":["apt","apt time","appointment","appointment time","del apt","del apt time"],"del_code":["del","del code","delivery code"],"agent_code":["agent","agent code"],"reference_no":["reference","reference no","ref","ref#"],"remark":["remark","remarks","notes"]}
def suggest_outbound_mapping(headers:list[str])->dict[str,str]:
 lookup={normalize(alias):field for field,aliases in OUTBOUND_ALIASES.items() for alias in aliases};return{h:lookup.get(normalize(h),"") for h in headers}
def validate_outbound_mapping(mapping:dict[str,str])->None:
 targets=[v for v in mapping.values() if v]
 if len(targets)!=len(set(targets)):raise ValueError("A system field cannot be mapped more than once")
 for required in ("warehouse","container_number"): 
  if required not in targets:raise ValueError(f"{required} mapping is required")

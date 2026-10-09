from dataclasses import dataclass

from app.models.import_job import ImportModule


def normalize_header(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("／", "/").split())


@dataclass(frozen=True)
class ImportProfile:
    code: str
    name: str
    module: ImportModule
    sheet_name: str
    mapping: dict[str, str]
    aliases: dict[str, tuple[str, ...]]
    required_targets: tuple[str, ...]

    def mapping_for(self, headers: list[str]) -> dict[str, str]:
        target_by_header: dict[str, str] = {}
        for source, target in {**self.mapping, **{"来源记录ID":"source_record_id", "业务单号":"business_document_id", "明细ID":"business_line_id", "预期版本":"expected_revision", "导入用途":"migration_mode", "货主":"customer"}}.items():
            target_by_header[normalize_header(source)] = target
        for target, values in self.aliases.items():
            for value in values:
                target_by_header[normalize_header(value)] = target
        return {header: target_by_header.get(normalize_header(header), "") for header in headers}


OL_MAPPING = {
    "柜号": "container_number", "仓点": "fc_code", "库位": "location",
    "板数": "pallet_qty", "件数": "carton_qty", "磅数(lb)": "weight_lbs",
    "体积": "cbm", "客户": "customer", "拆柜时间": "unload_date",
    "实际到仓时间": "received_date", "FBA": "fba_reference", "PO": "po_number",
    "备注": "remark", "重量(kg)": "weight_kg",
}
DS_MAPPING = {
    "客户": "customer", "柜号": "container_number", "ID / ST": "st_number",
    "FBA": "shipment_id", "PO": "po_number", "件数": "carton_qty",
    "LBS": "weight_lbs", "体积": "cbm", "派送仓点": "amazon_fc_code",
    "备注": "remark", "关联OL": "source_reference", "重量": "weight_unknown_unit",
}
OUTBOUND_MAPPING = {
    "计划单号": "ob_no", "仓点": "fc_code", "ISA/预约编号": "appointment_reference",
    "预计送仓时间": "delivery_appointment_time", "出库时间": "actual_outbound_time",
    "真实板数": "completed_pallet_qty", "拣货单": "picking_reference",
    "BOL": "bol_reference", "预计体积": "planned_cbm", "预计板数": "planned_pallet_qty",
    "重量(lb)": "planned_weight_lbs", "车队": "carrier", "Redirect Code": "redirect_code",
    "预计件数": "planned_carton_qty", "POD": "pod_reference", "PO": "po_number",
    "FBA": "fba_no", "真实件数": "completed_carton_qty",
    "真实重量": "completed_weight_lbs", "真实体积": "completed_cbm",
    "计划出库": "source_reference",
}

PROFILES: dict[str, ImportProfile] = {
    "WEST_COAST_4_0_OL": ImportProfile(
        "WEST_COAST_4_0_OL", "West Coast 4.0 OL", ImportModule.INBOUND, "OL", OL_MAPPING,
        {"weight_lbs": ("磅数(lb)", "磅数 (lb)"), "cbm": ("体积", "方数"), "fc_code": ("仓点",)},
        ("container_number", "fc_code"),
    ),
    "WEST_COAST_4_0_DS": ImportProfile(
        "WEST_COAST_4_0_DS", "West Coast 4.0 DS", ImportModule.FBA, "DS", DS_MAPPING,
        {"st_number": ("ID / ST", "ID/ST", "ID", "ST"), "weight_lbs": ("LBS", "lbs"), "shipment_id": ("FBA",)},
        ("container_number", "amazon_fc_code"),
    ),
    "WEST_COAST_4_0_OUTBOUND": ImportProfile(
        "WEST_COAST_4_0_OUTBOUND", "West Coast 4.0 Outbound", ImportModule.OUTBOUND, "出库", OUTBOUND_MAPPING,
        {"ob_no": ("计划单号",), "appointment_reference": ("ISA/预约编号", "ISA", "预约编号"),
         "pod_reference": ("POD", "POD_1"), "planned_weight_lbs": ("重量(lb)",)},
        ("ob_no", "fc_code"),
    ),
}


def get_profile(code: str | None) -> ImportProfile | None:
    return PROFILES.get(code or "")


def profiles_for_module(module: ImportModule) -> list[ImportProfile]:
    return [profile for profile in PROFILES.values() if profile.module == module]


def detect_workbook(sheet_names: list[str]) -> bool:
    return {"OL", "DS", "出库"}.issubset(set(sheet_names))


def suggest_profile(sheet_name: str, sheet_names: list[str]) -> str | None:
    if not detect_workbook(sheet_names):
        return None
    for profile in PROFILES.values():
        if profile.sheet_name == sheet_name:
            return profile.code
    return None

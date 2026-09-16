from datetime import UTC, date, datetime
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, BOL, BOLItem, OutboundInventoryAllocation, PickingList, PickingListItem
from app.models.bol import BOLStatus
from app.models.picking import PickingStatus
from app.schemas.picking_bol import BOLRead, PickComplete, PickingRead
from app.services.outbound import get_ob
from app.utils.business_time import get_business_today, to_business_date

PICK_NAMES = {0: "New", 1: "Printed", 2: "In Progress", 3: "Completed", 4: "Canceled", 5: "Exception"}
BOL_NAMES = {0: "Draft", 1: "Generated", 2: "Printed", 3: "Completed", 4: "Canceled"}
NAVY, BLUE, PALE_BLUE, PALE_YELLOW, GRID = "17324D", "1F4E78", "DDEBF7", "FFF2CC", "A6A6A6"


@dataclass(frozen=True)
class OutboundDocuments:
    picking: PickingList
    bol: BOL
    picking_list_created: bool
    bol_created: bool

    @property
    def documents_reused(self) -> bool:
        return not self.picking_list_created or not self.bol_created


def _active_picking(db: Session, ob_id: int):
    return db.scalar(
        select(PickingList)
        .where(PickingList.outbound_order_id == ob_id, PickingList.status != PickingStatus.CANCELED)
        .order_by(PickingList.id.desc())
    )


def _active_bol(db: Session, ob_id: int):
    return db.scalar(
        select(BOL)
        .where(BOL.outbound_order_id == ob_id, BOL.status != BOLStatus.CANCELED)
        .order_by(BOL.id.desc())
    )


def number(db, model, prefix):
    root = f"{prefix}{get_business_today():%y%m%d}"
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"picking-bol-number:{root}"})
    column = model.picking_no if model is PickingList else model.bol_no
    last = db.scalar(select(func.max(column)).where(column.like(root + "%")))
    return f"{root}{(int(last[-4:]) + 1 if last else 1):04d}"


def picking_read(p):
    return PickingRead.model_validate({**p.__dict__, "ob_no": p.outbound.ob_no, "status_name": PICK_NAMES[p.status], "planned_pallet_qty": sum((i.planned_pallet_qty for i in p.items), Decimal(0)), "planned_carton_qty": sum((i.planned_carton_qty for i in p.items), Decimal(0)), "picked_pallet_qty": sum((i.picked_pallet_qty for i in p.items), Decimal(0)), "picked_carton_qty": sum((i.picked_carton_qty for i in p.items), Decimal(0))})


def generate_picking(db: Session, ob_id, user_id, *, commit: bool = True):
    get_ob(db, ob_id)
    existing = _active_picking(db, ob_id)
    if existing:
        return existing
    allocs = list(db.scalars(select(OutboundInventoryAllocation).options(joinedload(OutboundInventoryAllocation.inventory_lot)).where(OutboundInventoryAllocation.outbound_order_id == ob_id)).all())
    if not allocs:
        raise HTTPException(409, "Outbound requires allocations")
    planned = []
    for seq, allocation in enumerate(sorted(allocs, key=lambda x: (x.inventory_lot.location_id or 0, x.inventory_lot.inbound_date or date.max)), 1):
        existing = db.scalars(select(PickingListItem).join(PickingList, PickingList.id == PickingListItem.picking_list_id).where(PickingListItem.outbound_allocation_id == allocation.id, PickingList.status != PickingStatus.CANCELED)).all()
        used_pallets = sum((i.planned_pallet_qty for i in existing), Decimal(0))
        used_cartons = sum((i.planned_carton_qty for i in existing), Decimal(0))
        pallets = allocation.allocated_pallet_qty - allocation.completed_pallet_qty - used_pallets
        cartons = allocation.allocated_carton_qty - allocation.completed_carton_qty - used_cartons
        if pallets <= 0 and cartons <= 0:
            continue
        lot = allocation.inventory_lot
        planned.append(PickingListItem(outbound_allocation_id=allocation.id, inventory_lot_id=lot.id, location_id=lot.location_id, lot_no=lot.lot_no, container_number=lot.container_number, fc_code=lot.fc_code, marking=lot.marking, planned_pallet_qty=pallets, planned_carton_qty=cartons, planned_weight_lbs=allocation.allocated_weight_lbs - allocation.completed_weight_lbs, planned_cbm=allocation.allocated_cbm - allocation.completed_cbm, sequence_no=seq))
    if not planned:
        existing = _active_picking(db, ob_id)
        if existing:
            return existing
        raise HTTPException(409, "Outbound has no quantity remaining to pick")
    p = PickingList(picking_no=number(db, PickingList, "PK"), outbound_order_id=ob_id, status=PickingStatus.NEW, created_by=user_id)
    p.items.extend(planned)
    db.add(p)
    db.flush()
    db.add(AuditLog(user_id=user_id, action="CREATE_PICKING_LIST", entity_type="PICKING", entity_id=p.id))
    if commit:
        db.commit()
    return p


def complete_picking(db: Session, pid: int, user_id: int, payload: PickComplete | None = None):
    p = db.get(PickingList, pid)
    if not p:
        raise HTTPException(404, "Picking list not found")
    if p.status in (3, 4):
        raise HTTPException(409, "Picking list is closed")
    for item in p.items:
        item.picked_pallet_qty = payload.picked_pallet_qty if payload and payload.picked_pallet_qty is not None else item.planned_pallet_qty
        item.picked_carton_qty = payload.picked_carton_qty if payload and payload.picked_carton_qty is not None else item.planned_carton_qty
    p.status = 3
    p.completed_at = datetime.now(UTC)
    p.completed_by = user_id
    db.add(AuditLog(user_id=user_id, action="COMPLETE_PICKING", entity_type="PICKING", entity_id=p.id))
    db.commit()
    return p


def _text(value, fallback=""):
    return str(value).strip() if value is not None and str(value).strip() else fallback


def _transport_mode(outbound):
    raw = " ".join(filter(None, (getattr(outbound, "delivery_type", None), getattr(outbound, "truck_type", None)))).upper()
    if any(word in raw for word in ("FTL", "FULL", "TRUCKLOAD")):
        return "FTL"
    if "LTL" in raw or "LESS" in raw:
        return "LTL"
    if any(word in raw for word in ("SPD", "PARCEL", "SMALL")):
        return "SPD"
    return "LTL/FTL" if getattr(outbound, "fba_shipment", None) else "FREIGHT"


def amazon_bol_context(b):
    """Map WMS data to Amazon freight reference fields without inventing identifiers."""
    outbound = b.outbound
    fba = getattr(b, "fba_shipment", None) or getattr(outbound, "fba_shipment", None)
    load = getattr(outbound, "load", None)
    carrier = getattr(b, "carrier", None) or getattr(outbound, "carrier", None) or getattr(load, "carrier", None)
    mode = _transport_mode(outbound)
    is_fba = bool(fba or getattr(outbound, "ob_type", "") == "FBA")
    context = {
        "is_fba": is_fba,
        "mode": mode,
        "outbound_no": _text(getattr(outbound, "ob_no", None)),
        "amazon_reference_id": _text(getattr(fba, "reference_no", None)),
        "shipment_id": _text(getattr(fba, "shipment_id", None)),
        "st_number": _text(getattr(fba, "st_number", None)),
        "po_number": _text(getattr(fba, "po_number", None) or getattr(outbound, "po_number", None)),
        "appointment_reference": _text(getattr(load, "appointment_reference", None) or getattr(outbound, "appointment_reference", None)),
        # This is the imported carrier document reference, not the WMS-generated BOL number.
        "carrier_tracking": _text(getattr(outbound, "bol_reference", None)),
        "carrier_name": _text(getattr(carrier, "carrier_name", None), "To be assigned"),
        "scac": _text(getattr(carrier, "scac", None)),
        "tractor_no": _text(getattr(load, "tractor_no", None) or getattr(outbound, "truck_number", None)),
        "trailer_no": _text(getattr(load, "trailer_no", None) or getattr(outbound, "trailer_number", None)),
        "seal_no": _text(getattr(load, "seal_no", None)),
        "pickup_date": _text(getattr(b, "pickup_date", None)),
        "appointment_time": _text(getattr(load, "appointment_time", None) or getattr(outbound, "delivery_appointment_time", None) or getattr(b, "appointment_time", None)),
    }
    missing = []
    if is_fba and mode != "SPD":
        for label, value in (("Amazon Reference ID", context["amazon_reference_id"]), ("FBA Shipment ID", context["shipment_id"]), ("Carrier PRO / tracking / BOL", context["carrier_tracking"])):
            if not value:
                missing.append(label)
        if mode == "FTL" and not context["seal_no"]:
            missing.append("Trailer seal number")
    if is_fba and (not b.ship_to_address or not b.amazon_fc_code):
        missing.append("Amazon FC destination")
    context["missing"] = missing
    context["ready"] = not missing
    return context


def bol_read(b):
    context = amazon_bol_context(b)
    return BOLRead.model_validate({**b.__dict__, "status_name": BOL_NAMES[b.status], "total_pallet_qty": sum((i.pallet_qty for i in b.items), Decimal(0)), "total_carton_qty": sum((i.carton_qty for i in b.items), Decimal(0)), "total_weight_lbs": sum((i.weight_lbs for i in b.items), Decimal(0)), "total_cbm": sum((i.cbm for i in b.items), Decimal(0)), "fc_address_missing": bool(b.amazon_fc_code and not b.ship_to_address), "transport_mode": context["mode"], "amazon_bol_ready": context["ready"], "missing_amazon_fields": context["missing"]})


def generate_bol(db: Session, ob_id, user_id, *, commit: bool = True):
    outbound = get_ob(db, ob_id)
    existing = _active_bol(db, ob_id)
    if existing:
        from app.services.operational_document import register_generated_bol
        if register_generated_bol(db, existing, user_id) and commit:
            db.commit()
        return existing
    warehouse = outbound.warehouse
    address = ", ".join(x for x in (warehouse.address, warehouse.city, warehouse.state, warehouse.zip_code, warehouse.country) if x)
    fba = outbound.fba_shipment
    fc_address = fba.amazon_fc_address if fba else None
    b = BOL(bol_no=number(db, BOL, "BOL"), outbound_order_id=ob_id, fba_shipment_id=outbound.fba_shipment_id, customer_id=outbound.customer_id, warehouse_id=outbound.warehouse_id, carrier_id=outbound.carrier_id, ship_from_name=warehouse.warehouse_name, ship_from_address=address, ship_to_name=fc_address.fc_name if fc_address else None, ship_to_address=", ".join(x for x in (fc_address.address_line1, fc_address.city, fc_address.state, fc_address.zip_code) if x) if fc_address else None, amazon_fc_code=outbound.fc_code or (fba.amazon_fc_code if fba else None), pickup_date=to_business_date(outbound.schedule_pickup_at), appointment_time=str(outbound.delivery_appointment_time) if outbound.delivery_appointment_time else None, status=BOLStatus.GENERATED, created_by=user_id)
    db.add(b)
    db.flush()
    for allocation in outbound.allocations:
        lot = allocation.inventory_lot
        b.items.append(BOLItem(outbound_allocation_id=allocation.id, inventory_lot_id=lot.id, container_number=lot.container_number, fc_code=lot.fc_code, marking=lot.marking, pallet_qty=allocation.allocated_pallet_qty - allocation.completed_pallet_qty, carton_qty=allocation.allocated_carton_qty - allocation.completed_carton_qty, weight_lbs=allocation.allocated_weight_lbs - allocation.completed_weight_lbs, cbm=allocation.allocated_cbm - allocation.completed_cbm, description="Outbound cargo"))
    from app.services.operational_document import register_generated_bol
    register_generated_bol(db, b, user_id)
    db.add(AuditLog(user_id=user_id, action="CREATE_BOL", entity_type="BOL", entity_id=b.id))
    if commit:
        db.commit()
    return b


def ensure_outbound_documents(db: Session, ob_id: int, user_id: int) -> OutboundDocuments:
    """Ensure one active document pair; the caller exclusively owns the transaction."""
    get_ob(db, ob_id, lock=True)
    picking = _active_picking(db, ob_id)
    bol = _active_bol(db, ob_id)
    picking_created = picking is None
    bol_created = bol is None
    if picking is None:
        picking = generate_picking(db, ob_id, user_id, commit=False)
    if bol is None:
        bol = generate_bol(db, ob_id, user_id, commit=False)
    db.flush()
    return OutboundDocuments(
        picking=picking,
        bol=bol,
        picking_list_created=picking_created,
        bol_created=bol_created,
    )


def _num(value, places=2):
    return round(float(value or 0), places)


def _bol_export_status(context):
    if context["ready"]:
        return "READY FOR DISPATCH"
    # Hide the FBA seal hint only in exports; readiness remains unchanged.
    missing = [label for label in context["missing"]
               if not (context["is_fba"] and label == "Trailer seal number")]
    return "PRE-DISPATCH CHECK" + (": " + "; ".join(missing) if missing else "")


def bol_xlsx(b):
    c = amazon_bol_context(b)
    wb = Workbook()
    ws = wb.active
    ws.title = "Amazon FBA BOL"
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A21"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.oddFooter.center.text = "DLX Yuki WMS | Amazon FBA Inbound BOL | Page &P of &N"
    for index, width in enumerate([5, 20, 13, 26, 22, 12, 14, 14, 13, 16], 1):
        ws.column_dimensions[get_column_letter(index)].width = width
    thin = Side(style="thin", color=GRID)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    title_fill, section_fill, label_fill = PatternFill("solid", fgColor=NAVY), PatternFill("solid", fgColor=BLUE), PatternFill("solid", fgColor=PALE_BLUE)

    def merge_value(cell_range, value, *, fill=None, font=None, align=None):
        ws.merge_cells(cell_range)
        cell = ws[cell_range.split(":")[0]]
        cell.value = value
        cell.font = font or Font()
        cell.alignment = align or Alignment(vertical="center", wrap_text=True)
        for row in ws[cell_range]:
            for item in row:
                item.border = border
                if fill:
                    item.fill = fill

    merge_value("A1:J2", "BILL OF LADING", fill=title_fill, font=Font(size=22, bold=True, color="FFFFFF"), align=Alignment(horizontal="center", vertical="center"))
    merge_value("A3:J3", f"AMAZON FBA INBOUND | {c['mode']} | WMS BOL {b.bol_no}", fill=label_fill, font=Font(size=11, bold=True, color=NAVY), align=Alignment(horizontal="center"))
    status = _bol_export_status(c)
    merge_value("A4:J4", status, fill=PatternFill("solid", fgColor="E2F0D9" if c["ready"] else PALE_YELLOW), font=Font(bold=True, color="006100" if c["ready"] else "9C6500"), align=Alignment(horizontal="center", wrap_text=True))
    merge_value("A6:E6", "SHIP FROM", fill=section_fill, font=Font(bold=True, color="FFFFFF"))
    merge_value("F6:J6", "SHIP TO - AMAZON FULFILLMENT CENTER", fill=section_fill, font=Font(bold=True, color="FFFFFF"))
    merge_value("A7:E7", f"{b.ship_from_name}\n{b.ship_from_address}")
    merge_value("F7:J7", f"{b.ship_to_name or 'Amazon FC'} ({b.amazon_fc_code or 'FC TBD'})\n{b.ship_to_address or 'Destination address required'}")
    ws.row_dimensions[7].height = 42
    merge_value("A9:J9", "AMAZON DELIVERY REFERENCES", fill=section_fill, font=Font(bold=True, color="FFFFFF"))
    references = [("Amazon Reference ID", c["amazon_reference_id"], "FBA Shipment ID", c["shipment_id"]), ("ST Number", c["st_number"], "PO Number", c["po_number"]), ("WMS BOL Number", b.bol_no, "Outbound Number", c["outbound_no"]), ("Pickup Date", c["pickup_date"], "Appointment / Time", " / ".join(filter(None, (c["appointment_reference"], c["appointment_time"]))))]
    for row_no, row in enumerate(references, 10):
        l1, v1, l2, v2 = row
        merge_value(f"A{row_no}:B{row_no}", l1, fill=label_fill, font=Font(bold=True)); merge_value(f"C{row_no}:E{row_no}", v1 or "REQUIRED")
        merge_value(f"F{row_no}:G{row_no}", l2, fill=label_fill, font=Font(bold=True)); merge_value(f"H{row_no}:J{row_no}", v2 or "REQUIRED")
    merge_value("A15:J15", "CARRIER AND EQUIPMENT", fill=section_fill, font=Font(bold=True, color="FFFFFF"))
    carrier_rows = [("Carrier", c["carrier_name"], "SCAC", c["scac"]), ("PRO / Tracking / Carrier BOL", c["carrier_tracking"], "Tractor / Trailer", " / ".join(filter(None, (c["tractor_no"], c["trailer_no"])))), ("" if c["is_fba"] else "Trailer Seal (FTL)", "" if c["is_fba"] else c["seal_no"], "Transport Mode", c["mode"])]
    for row_no, row in enumerate(carrier_rows, 16):
        l1, v1, l2, v2 = row
        merge_value(f"A{row_no}:B{row_no}", l1, fill=label_fill, font=Font(bold=True)); merge_value(f"C{row_no}:E{row_no}", (v1 or "TO BE PROVIDED") if l1 else "")
        merge_value(f"F{row_no}:G{row_no}", l2, fill=label_fill, font=Font(bold=True)); merge_value(f"H{row_no}:J{row_no}", v2 or "TO BE PROVIDED")
    headers = ["#", "" if c["is_fba"] else "Container", "FC", "Marking", "Commodity", "Pallets", "Cartons", "Weight (lb)", "CBM", "Freight Class"]
    for col, value in enumerate(headers, 1):
        cell = ws.cell(20, col, value); cell.fill = section_fill; cell.font = Font(bold=True, color="FFFFFF"); cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True); cell.border = border
    for row_no, item in enumerate(b.items, 21):
        values = [row_no - 20, "" if c["is_fba"] else item.container_number or "", item.fc_code or b.amazon_fc_code or "", item.marking or "", item.description or "General merchandise", _num(item.pallet_qty), _num(item.carton_qty), _num(item.weight_lbs), _num(item.cbm, 4), ""]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row_no, col, value); cell.border = border; cell.alignment = Alignment(horizontal="center" if col != 5 else "left", vertical="center", wrap_text=True)
    total_row = 21 + len(b.items)
    merge_value(f"A{total_row}:E{total_row}", "TOTAL", fill=label_fill, font=Font(bold=True), align=Alignment(horizontal="right"))
    for col in range(6, 10):
        letter_col = get_column_letter(col); cell = ws.cell(total_row, col, f"=SUM({letter_col}21:{letter_col}{total_row - 1})" if b.items else 0); cell.fill = label_fill; cell.font = Font(bold=True); cell.border = border; cell.alignment = Alignment(horizontal="center")
    ws.cell(total_row, 10).border = border; ws.cell(total_row, 10).fill = label_fill
    notes_row = total_row + 2
    merge_value(f"A{notes_row}:J{notes_row}", "AMAZON DELIVERY NOTES", fill=section_fill, font=Font(bold=True, color="FFFFFF"))
    notes = "Non-partner carriers must schedule a delivery appointment. Provide the Amazon Reference ID, FBA Shipment ID, and carrier PRO/tracking/BOL number to the carrier and on delivery. Keep Amazon box and pallet labels visible. FTL/intermodal loads require a trailer seal. This WMS document does not replace an Amazon Partnered Carrier-issued BOL."
    if c["is_fba"]:
        notes = notes.replace(" FTL/intermodal loads require a trailer seal.", "")
    merge_value(f"A{notes_row + 1}:J{notes_row + 2}", notes); ws.row_dimensions[notes_row + 1].height = 42
    signature_row = notes_row + 4
    merge_value(f"A{signature_row}:C{signature_row}", "Shipper signature / date"); merge_value(f"D{signature_row}:G{signature_row}", "Carrier signature / pickup date"); merge_value(f"H{signature_row}:J{signature_row}", "Consignee signature / delivery date")
    ws.print_area = f"A1:J{signature_row}"
    output = BytesIO(); wb.save(output); return output.getvalue()


def bol_pdf(b):
    c = amazon_bol_context(b)
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=.42 * inch, leftMargin=.42 * inch, topMargin=.36 * inch, bottomMargin=.44 * inch, title=f"Amazon FBA Inbound BOL {b.bol_no}", author="DLX Yuki WMS")
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("bol-normal", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=9.5)
    small = ParagraphStyle("bol-small", parent=normal, fontSize=6.4, leading=8)
    white = ParagraphStyle("bol-white", parent=normal, textColor=colors.white, fontName="Helvetica-Bold")
    center = ParagraphStyle("bol-center", parent=normal, alignment=TA_CENTER)
    right = ParagraphStyle("bol-right", parent=normal, alignment=TA_RIGHT)
    title = ParagraphStyle("bol-title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=22, textColor=colors.HexColor("#17324D"), spaceAfter=1)
    subtitle = ParagraphStyle("bol-subtitle", parent=center, fontName="Helvetica-Bold", fontSize=8, textColor=colors.HexColor("#1F4E78"), spaceAfter=5)

    def p(value, style=normal):
        safe = _text(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        return Paragraph(safe or "&nbsp;", style)

    def section(text):
        table = Table([[p(text, white)]], colWidths=[7.65 * inch], rowHeights=[.22 * inch])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1F4E78")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        return table

    def details(rows):
        data = [[p(l1, small), p((v1 or "REQUIRED") if l1 else ""), p(l2, small), p(v2 or "REQUIRED")] for l1, v1, l2, v2 in rows]
        table = Table(data, colWidths=[1.18 * inch, 2.64 * inch, 1.18 * inch, 2.65 * inch])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#A6A6A6")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#DDEBF7")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#DDEBF7")), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return table

    story = [p("BILL OF LADING", title), p(f"AMAZON FBA INBOUND | {c['mode']} | WMS BOL {b.bol_no}", subtitle)]
    status_text = _bol_export_status(c)
    status = Table([[p(status_text, center)]], colWidths=[7.65 * inch])
    status.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E2F0D9" if c["ready"] else "#FFF2CC")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#A6A6A6")), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    address = Table([[p("SHIP FROM", white), p("SHIP TO - AMAZON FULFILLMENT CENTER", white)], [p(f"{b.ship_from_name}\n{b.ship_from_address}"), p(f"{b.ship_to_name or 'Amazon FC'} ({b.amazon_fc_code or 'FC TBD'})\n{b.ship_to_address or 'Destination address required'}")]], colWidths=[3.825 * inch] * 2)
    address.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#A6A6A6")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([status, Spacer(1, 5), address, Spacer(1, 5), section("AMAZON DELIVERY REFERENCES"), details([("Amazon Reference ID", c["amazon_reference_id"], "FBA Shipment ID", c["shipment_id"]), ("ST Number", c["st_number"], "PO Number", c["po_number"]), ("WMS BOL Number", b.bol_no, "Outbound Number", c["outbound_no"]), ("Pickup Date", c["pickup_date"], "Appointment / Time", " / ".join(filter(None, (c["appointment_reference"], c["appointment_time"]))))]), Spacer(1, 5), section("CARRIER AND EQUIPMENT"), details([("Carrier", c["carrier_name"], "SCAC", c["scac"]), ("PRO / Tracking / Carrier BOL", c["carrier_tracking"] or "TO BE PROVIDED", "Tractor / Trailer", " / ".join(filter(None, (c["tractor_no"], c["trailer_no"]))) or "TO BE PROVIDED"), ("" if c["is_fba"] else "Trailer Seal (FTL)", "" if c["is_fba"] else c["seal_no"] or "TO BE PROVIDED", "Transport Mode", c["mode"])]), Spacer(1, 6), section("CARGO DETAILS")])
    cargo = [[p(x, white) for x in ("#", "" if c["is_fba"] else "Container", "FC", "Marking", "Commodity", "PLT", "CTN", "Weight lb", "CBM")]]
    totals = [Decimal(0)] * 4
    for index, item in enumerate(b.items, 1):
        totals = [totals[0] + (item.pallet_qty or 0), totals[1] + (item.carton_qty or 0), totals[2] + (item.weight_lbs or 0), totals[3] + (item.cbm or 0)]
        cargo.append([p(index, center), p("" if c["is_fba"] else item.container_number, small), p(item.fc_code or b.amazon_fc_code, center), p(item.marking, small), p(item.description or "General merchandise", small), p(f"{_num(item.pallet_qty):g}", right), p(f"{_num(item.carton_qty):g}", right), p(f"{_num(item.weight_lbs):,.2f}", right), p(f"{_num(item.cbm, 4):,.4f}", right)])
    cargo.append([p("TOTAL", right), "", "", "", "", p(f"{_num(totals[0]):g}", right), p(f"{_num(totals[1]):g}", right), p(f"{_num(totals[2]):,.2f}", right), p(f"{_num(totals[3], 4):,.4f}", right)])
    cargo_table = Table(cargo, colWidths=[.25 * inch, 1.12 * inch, .45 * inch, .75 * inch, 2.22 * inch, .52 * inch, .52 * inch, 1.05 * inch, .77 * inch], repeatRows=1)
    cargo_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#A6A6A6")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("SPAN", (0, -1), (4, -1)), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DDEBF7")), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.extend([cargo_table, Spacer(1, 6), section("AMAZON DELIVERY NOTES")])
    notes = "Non-partner carriers must schedule a delivery appointment. Provide the Amazon Reference ID, FBA Shipment ID, and carrier PRO/tracking/BOL number to the carrier and on delivery. Keep Amazon box and pallet labels visible. FTL/intermodal loads require a trailer seal. This WMS document does not replace an Amazon Partnered Carrier-issued BOL."
    if c["is_fba"]:
        notes = notes.replace(" FTL/intermodal loads require a trailer seal.", "")
    notes_table = Table([[p(notes, small)]], colWidths=[7.65 * inch]); notes_table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .35, colors.HexColor("#A6A6A6")), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    signature = Table([[p("Shipper signature / date", small), p("Carrier signature / pickup date", small), p("Consignee signature / delivery date", small)], ["", "", ""]], colWidths=[2.55 * inch] * 3, rowHeights=[.24 * inch, .48 * inch])
    signature.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#A6A6A6")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([notes_table, Spacer(1, 7), KeepTogether(signature)])

    def footer(canvas, document):
        canvas.saveState(); canvas.setFont("Helvetica", 6.5); canvas.setFillColor(colors.HexColor("#666666")); canvas.drawCentredString(letter[0] / 2, .23 * inch, f"DLX Yuki WMS | Amazon FBA Inbound BOL | Page {document.page}"); canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()

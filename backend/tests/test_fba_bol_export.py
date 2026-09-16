from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as NS

import pytest
from openpyxl import load_workbook
from reportlab.platypus import KeepTogether, Paragraph, Table

from app.services import picking_bol as service


def sample_bol(kind="fba_type", seal="HIST-SEAL-987"):
    fba = NS(reference_no="AMZ-REF", shipment_id="SHIP-123", st_number="ST-456", po_number="PO-789") if kind == "fba_relation" else None
    outbound = NS(ob_type="FBA" if kind == "fba_type" else "OTHER", fba_shipment=fba,
                  load=NS(seal_no=seal, tractor_no="TRACTOR-1", trailer_no="TRAILER-2"),
                  delivery_type="FTL", ob_no="OB-SAMPLE", bol_reference="PRO-123", po_number="PO-789")
    return NS(outbound=outbound, fba_shipment=fba, carrier=NS(carrier_name="Sample Carrier", scac="TEST"),
              bol_no="BOL-SAMPLE", ship_from_name="Sample Warehouse", ship_from_address="1 Sample Way",
              ship_to_name="Sample FC", ship_to_address="2 Example Road", amazon_fc_code="ONT8",
              pickup_date="2026-09-16", items=[NS(container_number="HIST-CNTR-123", fc_code="ONT8",
              marking="MARK-1", description="Sample merchandise", pallet_qty=Decimal(2), carton_qty=Decimal(20),
              weight_lbs=Decimal(100), cbm=Decimal(1))])


def export_text(bol, format, monkeypatch):
    if format == "xlsx":
        ws = load_workbook(BytesIO(service.bol_xlsx(bol))).active
        return "\n".join(str(cell.value) for row in ws for cell in row if cell.value is not None)
    captured = []
    def visit(value):
        if isinstance(value, Paragraph):
            captured.append(value.getPlainText())
        elif isinstance(value, Table):
            visit(value._cellvalues)
        elif isinstance(value, KeepTogether):
            visit(value._content)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
    monkeypatch.setattr(service.SimpleDocTemplate, "build", lambda self, story, **kw: visit(story))
    service.bol_pdf(bol)
    return "\n".join(captured)


@pytest.mark.parametrize("format", ["pdf", "xlsx"])
@pytest.mark.parametrize("kind", ["fba_type", "fba_relation", "other"])
@pytest.mark.parametrize("seal", ["HIST-SEAL-987", ""])
def test_export_scope_and_readiness(format, kind, seal, monkeypatch):
    bol = sample_bol(kind, seal)
    before = service.amazon_bol_context(bol)
    text = export_text(bol, format, monkeypatch)
    assert service.amazon_bol_context(bol) == before
    assert bol.items[0].container_number == "HIST-CNTR-123"
    assert bol.outbound.load.seal_no == seal
    for retained in ["BOL-SAMPLE", "OB-SAMPLE", "PRO-123", "TRACTOR-1", "TRAILER-2", "MARK-1", "Sample merchandise", "PO-789"]:
        assert retained in text
    if kind != "other":
        assert "container" not in text.lower()
        assert "seal" not in text.lower()
        assert "HIST-CNTR-123" not in text
        assert "TO BE PROVIDED" not in text
        if not seal:
            assert "Trailer seal number" in before["missing"]
            assert not before["ready"]
            assert "PRE-DISPATCH CHECK" in text
        if kind == "fba_relation" and not seal:
            assert before["missing"] == ["Trailer seal number"]
        if kind == "fba_type":
            assert "Amazon Reference ID; FBA Shipment ID" in text
    else:
        assert "Container" in text and "HIST-CNTR-123" in text
        assert "Trailer Seal (FTL)" in text
        assert "FTL/intermodal loads require a trailer seal." in text
        assert (seal or "TO BE PROVIDED") in text


def test_fba_snapshot_and_picking_container_preserved(client, seed, db):
    from app.models import BOL, OutboundOrder
    from test_picking_bol import make_ob
    outbound, _ = make_ob(client, seed, "-FBA-EXPORT")
    db.get(OutboundOrder, outbound["id"]).ob_type = "FBA"
    db.commit()
    docs = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").json()
    bol = db.get(BOL, docs["bol_id"])
    assert bol.items[0].container_number == "PK-CNTR-FBA-EXPORT"
    for format in ("pdf", "xlsx"):
        assert client.get(f"/api/v1/bols/{bol.id}/{format}").status_code == 200
    assert bol.items[0].container_number == "PK-CNTR-FBA-EXPORT"
    response = client.get(f"/api/v1/picking-lists/{docs['picking_list_id']}/xlsx")
    assert response.status_code == 200
    ws = load_workbook(BytesIO(response.content)).active
    assert ws["E1"].value == "Container"
    assert ws["E2"].value == "PK-CNTR-FBA-EXPORT"

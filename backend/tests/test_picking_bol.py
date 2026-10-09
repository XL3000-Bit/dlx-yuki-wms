from datetime import date
from fastapi.testclient import TestClient
from io import BytesIO
from zipfile import ZipFile

def test_document_package_is_printable_and_idempotent(client, seed, db):
    ob = make_ob(client, seed)
    before = client.get(f"/api/v1/outbounds/{ob['id']}").json()
    for _ in range(2):
        response = client.post(f"/api/v1/outbounds/{ob['id']}/documents/package")
        assert response.status_code == 200, response.text
        assert response.headers['content-type'] == 'application/zip'
        with ZipFile(BytesIO(response.content)) as archive:
            assert len(archive.namelist()) == 2
            assert all(archive.read(name).startswith(b'%PDF-') for name in archive.namelist())
    assert len(client.get('/api/v1/picking-lists').json()) == 1
    assert len(client.get('/api/v1/bols').json()) == 1
    from sqlalchemy import select
    from app.models import BOLItem, PickingListItem
    assert db.scalar(select(BOLItem)).container_number == "PK-CNTR"
    assert db.scalar(select(PickingListItem)).container_number == "PK-CNTR"
    payload = client.get('/api/v1/bols').json()[0]
    assert not any('container' in key.lower() or 'seal' in key.lower() for key in payload)
    after = client.get(f"/api/v1/outbounds/{ob['id']}").json()
    assert after == before
    picking = client.get('/api/v1/picking-lists').json()[0]
    assert picking['status'] == 0
    pdf = client.get(f"/api/v1/picking-lists/{picking['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b'%PDF-')

def test_document_package_requires_allocation(client, seed):
    ob = client.post('/api/v1/outbounds', json={'warehouse_id': seed['warehouse'].id, 'customer_id': seed['customer'].id}).json()
    response = client.post(f"/api/v1/outbounds/{ob['id']}/documents/package")
    assert response.status_code == 409
    assert client.get('/api/v1/picking-lists').json() == []
    assert client.get('/api/v1/bols').json() == []

def test_document_package_rejects_stale_quantities(client, seed, db):
    from sqlalchemy import select
    from app.models.bol import BOLItem
    ob = make_ob(client, seed)
    assert client.post(f"/api/v1/outbounds/{ob['id']}/documents/package").status_code == 200
    item = db.scalar(select(BOLItem))
    item.carton_qty = 1
    db.commit()
    assert client.post(f"/api/v1/outbounds/{ob['id']}/documents/package").status_code == 409
def make_ob(client,seed):
 p={'container_number':'PK-CNTR','customer_id':seed['customer'].id,'warehouse_id':seed['warehouse'].id,'received_date':str(date.today()),'fc_code':'ONT8','pallet_qty':10,'carton_qty':20,'weight_lbs':100,'cbm':2,'location_id':seed['location'].id,'status':3};ib=client.post('/api/v1/inbound',json=p).json();lot=client.post(f"/api/v1/inbound/{ib['id']}/receive-to-inventory").json();ob=client.post('/api/v1/outbounds',json={'warehouse_id':seed['warehouse'].id,'customer_id':seed['customer'].id,'carrier_id':seed['carrier'].id}).json();client.post(f"/api/v1/outbounds/{ob['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':10,'carton_qty':20});return ob
def test_picking_and_bol_snapshot(client:TestClient,seed):
 ob=make_ob(client,seed);p=client.post(f"/api/v1/outbounds/{ob['id']}/picking-lists");assert p.status_code==200,p.text;assert p.json()['picking_no'].startswith('PK');assert p.json()['planned_pallet_qty']=='10.00';second=client.post(f"/api/v1/outbounds/{ob['id']}/picking-lists");assert second.status_code==200,second.text;assert second.json()['id']==p.json()['id'];assert second.json()['planned_pallet_qty']=='10.00';assert client.post(f"/api/v1/picking-lists/{p.json()['id']}/complete",json={}).status_code==200;bol=client.post(f"/api/v1/outbounds/{ob['id']}/bol");assert bol.status_code==200,bol.text;assert bol.json()['total_pallet_qty']=='10.00';assert bol.json()['transport_mode']=='FREIGHT';assert bol.json()['amazon_bol_ready'] is True;assert bol.json()['missing_amazon_fields']==[];assert client.get(f"/api/v1/bols/{bol.json()['id']}/pdf").headers['content-type']=='application/pdf';assert client.get(f"/api/v1/bols/{bol.json()['id']}/xlsx").status_code==200;documents=client.get('/api/v1/documents',params={'bol_id':bol.json()['id']});assert documents.status_code==200,documents.text;registered=documents.json()['data'];assert len(registered)==1;assert registered[0]['document_type']=='BOL';assert registered[0]['is_generated'] is True;assert client.get(f"/api/v1/documents/{registered[0]['id']}/download").headers['content-type']=='application/pdf'


def test_confirm_auto_issues_documents_idempotently(client: TestClient, seed):
    outbound = make_ob(client, seed)

    confirmed = client.post(f"/api/v1/outbounds/{outbound['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text

    pickings = client.get("/api/v1/picking-lists").json()
    bols = client.get("/api/v1/bols").json()
    picking = next(item for item in pickings if item["outbound_order_id"] == outbound["id"])
    bol = next(item for item in bols if item["outbound_order_id"] == outbound["id"])

    first = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure")
    second = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["picking"]["id"] == picking["id"] == second.json()["picking"]["id"]
    assert first.json()["bol"]["id"] == bol["id"] == second.json()["bol"]["id"]

    queue = client.get("/api/v1/3pl/dispatch-queue")
    assert queue.status_code == 200, queue.text
    task = next(item for item in queue.json()["tasks"] if item["id"] == outbound["id"])
    assert task["document_state"] == "READY"
    assert task["picking_id"] == picking["id"]
    assert task["bol_id"] == bol["id"]

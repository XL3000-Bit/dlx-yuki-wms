from app.models import ImportJob, ImportRow
from app.models.import_job import ImportModule, ImportStatus


def test_archive_search_pagination_and_access(client, db, seed):
    archive = ImportJob(module=ImportModule.INBOUND, file_name='source.xlsx', original_file_name='source.xlsx',
        profile_code='WEST_COAST_4_0_HISTORY', source_sheet='OL', status=ImportStatus.COMPLETED,
        created_by=seed['admin'].id, total_rows=2, detected_columns=['柜号'])
    other = ImportJob(module=ImportModule.INBOUND, file_name='other.xlsx', original_file_name='other.xlsx', created_by=seed['admin'].id)
    db.add_all([archive, other]); db.flush()
    db.add_all([ImportRow(import_job_id=archive.id, row_number=2, raw_data={'柜号': 'TEST%柜'}),
                ImportRow(import_job_id=archive.id, row_number=5, raw_data={'柜号': 'TEST123'})]); db.commit()
    assert len(client.get('/api/v1/history-archive').json()) == 1
    result = client.get(f'/api/v1/history-archive/{archive.id}/records', params={'q': '%'}).json()
    assert result['total'] == 1
    assert result['rows'][0]['data']['柜号'] == 'TEST%柜'
    result = client.get(f'/api/v1/history-archive/{archive.id}/records?page=2&page_size=1').json()
    assert result['total'] == 2 and result['rows'][0]['row_number'] == 5
    assert client.get(f'/api/v1/history-archive/{other.id}/records').status_code == 404
    assert client.get(f'/api/v1/history-archive/{archive.id}/records?page_size=999').status_code == 422
    assert client.get(f'/api/v1/history-archive/{archive.id}/source').status_code == 404
    client.headers.pop('Authorization')
    assert client.get('/api/v1/history-archive').status_code == 401
import pytest
from app.models import Customer, Warehouse
from app.models.user import ScopeMode
from app.core.security import create_access_token

@pytest.fixture
def scoped_archive(client, db, seed):
    warehouse = Warehouse(warehouse_code="OTHER", warehouse_name="Other warehouse", address="2 Way", city="LA", state="CA", zip_code="90001")
    customer = Customer(customer_code="OTHER", customer_name="Other customer")
    db.add_all([warehouse, customer]); db.flush()
    jobs = []
    for wh in [seed["warehouse"], warehouse]:
        job = ImportJob(module=ImportModule.INBOUND, file_name="scope.xlsx", original_file_name="scope.xlsx", profile_code="WEST_COAST_4_0_HISTORY", source_sheet=wh.warehouse_code, created_by=seed["admin"].id, options={"warehouse_id": wh.id, "warehouse_name": wh.warehouse_name})
        db.add(job); db.flush(); jobs.append(job)
        for number, name in enumerate([seed["customer"].customer_name, customer.customer_name, "Unmapped"], 1):
            db.add(ImportRow(import_job_id=job.id, row_number=number, raw_data={"客户": name}))
    viewer = seed["viewer"]
    viewer.warehouse_scope_mode = ScopeMode.SELECTED
    viewer.customer_scope_mode = ScopeMode.SELECTED
    viewer.warehouses = [seed["warehouse"]]
    viewer.customers = [seed["customer"]]
    db.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(str(viewer.id))}"
    return jobs, warehouse, customer, viewer

def test_archive_allowed_warehouse_and_customer(client, seed, scoped_archive):
    jobs, _, _, _ = scoped_archive
    response = client.get("/api/v1/history-archive", params={"warehouse_id": seed["warehouse"].id, "customer_id": seed["customer"].id})
    assert response.status_code == 200
    assert [(r["id"], r["total_rows"]) for r in response.json()] == [(jobs[0].id, 1)]

def test_archive_denies_explicit_warehouse(client, scoped_archive):
    jobs, warehouse, _, _ = scoped_archive
    assert client.get("/api/v1/history-archive", params={"warehouse_id": warehouse.id}).status_code == 403
    assert client.get(f"/api/v1/history-archive/{jobs[1].id}/records").status_code == 403

def test_archive_denies_explicit_customer(client, scoped_archive):
    jobs, _, customer, _ = scoped_archive
    for url in ["/api/v1/history-archive", f"/api/v1/history-archive/{jobs[0].id}/records"]:
        assert client.get(url, params={"customer_id": customer.id}).status_code == 403

def test_archive_implicit_scope_filters_counts_and_pages(client, seed, scoped_archive):
    jobs, _, _, _ = scoped_archive
    assert len(client.get("/api/v1/history-archive").json()) == 1
    url = f"/api/v1/history-archive/{jobs[0].id}/records"
    result = client.get(url, params={"page_size": 1}).json()
    assert result["total"] == 1
    assert result["rows"][0]["data"]["客户"] == seed["customer"].customer_name
    assert client.get(url, params={"page_size": 1, "page": 2}).json()["rows"] == []
    assert client.get(url, params={"q": "Other customer"}).json()["total"] == 0

@pytest.mark.parametrize("scope", ["warehouse", "customer"])
def test_archive_empty_selected_scope(client, db, scoped_archive, scope):
    jobs, _, _, viewer = scoped_archive
    setattr(viewer, scope + "s", [])
    db.commit()
    assert client.get("/api/v1/history-archive").json() == []
    response = client.get(f"/api/v1/history-archive/{jobs[0].id}/records")
    if scope == "warehouse": assert response.status_code == 403
    else: assert response.json() == {"total": 0, "rows": []}

def test_archive_admin_bypasses_selected_empty_scopes(client, db, seed, scoped_archive):
    jobs, _, _, _ = scoped_archive
    admin = seed["admin"]
    admin.warehouse_scope_mode = admin.customer_scope_mode = ScopeMode.SELECTED
    db.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(str(admin.id))}"
    assert len(client.get("/api/v1/history-archive").json()) == 2
    assert client.get(f"/api/v1/history-archive/{jobs[1].id}/records").json()["total"] == 3

def test_archive_scoped_source_download_denied(client, scoped_archive):
    jobs, _, _, _ = scoped_archive
    for job in jobs:
        assert client.get(f"/api/v1/history-archive/{job.id}/source").status_code == 403

def test_archive_ambiguous_customer_name_fails_closed(client, db, seed, scoped_archive):
    jobs, _, _, _ = scoped_archive
    db.add(Customer(customer_code="DUPLICATE", customer_name=seed["customer"].customer_name)); db.commit()
    assert client.get(f"/api/v1/history-archive/{jobs[0].id}/records").json()["total"] == 0

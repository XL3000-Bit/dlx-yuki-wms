from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_openapi_contains_phase1_routes() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/users/bootstrap" in paths
    assert "/api/v1/master-data/warehouse-locations" in paths
    assert "/api/v1/master-data/amazon-fc-addresses/{fc_code}" in paths

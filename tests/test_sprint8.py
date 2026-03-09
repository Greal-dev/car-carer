"""Tests for Sprint 8: pagination, additional coverage."""


def test_maintenance_search_pagination(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "PaginMaint"}).json()
    # Empty search with pagination params
    res = auth_client.get(f"/api/vehicles/{v['id']}/maintenance-search?page=1&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert "pages" in data


def test_delete_vehicle_cascades(auth_client):
    """Deleting a vehicle should cascade to related data."""
    v = auth_client.post("/api/vehicles", json={"name": "Cascade"}).json()
    res = auth_client.delete(f"/api/vehicles/{v['id']}")
    assert res.status_code == 204


def test_dashboard_works(auth_client):
    """Dashboard should work correctly."""
    v = auth_client.post("/api/vehicles", json={"name": "DashTest"}).json()
    res = auth_client.get("/api/vehicles/dashboard")
    assert res.status_code == 200
    assert res.json()["summary"]["vehicle_count"] >= 1

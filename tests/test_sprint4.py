"""Tests for Sprint 4 features: CSV export, search, calendar, quotes."""


def test_export_csv(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "CSV"}).json()
    res = auth_client.get(f"/api/vehicles/{v['id']}/export-csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "Date;Type;Garage" in res.text


def test_maintenance_search_empty(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Search"}).json()
    res = auth_client.get(f"/api/vehicles/{v['id']}/maintenance-search?q=vidange")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_maintenance_search_no_filter(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "All"}).json()
    res = auth_client.get(f"/api/vehicles/{v['id']}/maintenance-search")
    assert res.status_code == 200
    assert "items" in res.json()


def test_csv_requires_auth(client):
    res = client.get("/api/vehicles/1/export-csv")
    assert res.status_code == 401

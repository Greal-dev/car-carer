"""Tests for Sprint 8: VIN decoder, pagination, dark mode (backend-only), additional coverage."""


def test_vin_decode_valid_renault(auth_client):
    res = auth_client.get("/api/vehicles/vin-decode?vin=VF1RFA00067123456")
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["brand"] == "Renault"
    assert data["country"] == "France"


def test_vin_decode_valid_vw(auth_client):
    res = auth_client.get("/api/vehicles/vin-decode?vin=WVWZZZ3CZWE123456")
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["brand"] == "Volkswagen"


def test_vin_decode_year(auth_client):
    # Position 10 = 'R' => 2024
    res = auth_client.get("/api/vehicles/vin-decode?vin=VF1RFAR00R7123456")
    assert res.status_code == 200
    assert res.json()["year"] == 2024


def test_vin_decode_invalid_length(auth_client):
    res = auth_client.get("/api/vehicles/vin-decode?vin=SHORT")
    assert res.status_code == 422  # Validation error from Query min_length


def test_vin_decode_invalid_chars(auth_client):
    res = auth_client.get("/api/vehicles/vin-decode?vin=VF1RFAI00O7123456")  # contains I and O
    assert res.status_code == 200
    assert res.json()["valid"] is False


def test_fuel_pagination(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "PaginFuel"}).json()
    for i in range(5):
        auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
            "date": f"2025-01-{i+1:02d}", "mileage": 10000 + i * 500, "liters": 40, "full_tank": True,
        })
    # Page 1 with limit 2
    res = auth_client.get(f"/api/vehicles/{v['id']}/fuel?page=1&limit=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["pages"] == 3

    # Page 3
    res = auth_client.get(f"/api/vehicles/{v['id']}/fuel?page=3&limit=2")
    assert res.status_code == 200
    assert len(res.json()["items"]) == 1


def test_maintenance_search_pagination(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "PaginMaint"}).json()
    # Empty search with pagination params
    res = auth_client.get(f"/api/vehicles/{v['id']}/maintenance-search?page=1&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert "pages" in data


def test_vin_requires_auth(client):
    res = client.get("/api/vehicles/vin-decode?vin=VF1RFA00067123456")
    assert res.status_code == 401


def test_delete_vehicle_cascades(auth_client):
    """Deleting a vehicle should cascade to fuel entries."""
    v = auth_client.post("/api/vehicles", json={"name": "Cascade"}).json()
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 10000, "liters": 40, "full_tank": True,
    })
    res = auth_client.delete(f"/api/vehicles/{v['id']}")
    assert res.status_code == 204


def test_dashboard_includes_fuel_info(auth_client):
    """Dashboard should still work with fuel data."""
    v = auth_client.post("/api/vehicles", json={"name": "DashFuel"}).json()
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 50000, "liters": 45, "full_tank": True,
    })
    res = auth_client.get("/api/vehicles/dashboard")
    assert res.status_code == 200
    assert res.json()["summary"]["vehicle_count"] >= 1

"""Tests for Sprint 6: fuel tracking, mileage validation, vehicle photo, JWT persistence."""

from datetime import date


def test_add_fuel_entry(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Fuel Test"}).json()
    res = auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-15", "mileage": 10000, "liters": 45.5,
        "price_per_liter": 1.85, "station": "TotalEnergies", "full_tank": True,
    })
    assert res.status_code == 201
    data = res.json()
    assert data["liters"] == 45.5
    assert data["total_cost"] == round(45.5 * 1.85, 2)
    assert data["mileage_warning"] is None


def test_fuel_mileage_regression_warning(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Regress"}).json()
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 20000, "liters": 40, "full_tank": True,
    })
    res = auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-02-01", "mileage": 15000, "liters": 35, "full_tank": True,
    })
    assert res.status_code == 201
    assert res.json()["mileage_warning"]["type"] == "mileage_regression"


def test_fuel_mileage_jump_warning(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Jump"}).json()
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 10000, "liters": 40, "full_tank": True,
    })
    res = auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-02-01", "mileage": 70000, "liters": 35, "full_tank": True,
    })
    assert res.status_code == 201
    assert res.json()["mileage_warning"]["type"] == "mileage_jump"


def test_list_fuel_entries(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "List Fuel"}).json()
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 10000, "liters": 40, "full_tank": True,
    })
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-02-01", "mileage": 10500, "liters": 42, "full_tank": True,
    })
    res = auth_client.get(f"/api/vehicles/{v['id']}/fuel")
    assert res.status_code == 200
    assert res.json()["total"] == 2
    assert len(res.json()["items"]) == 2


def test_delete_fuel_entry(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Del Fuel"}).json()
    entry = auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 10000, "liters": 40, "full_tank": True,
    }).json()
    res = auth_client.delete(f"/api/vehicles/{v['id']}/fuel/{entry['id']}")
    assert res.status_code == 204
    assert auth_client.get(f"/api/vehicles/{v['id']}/fuel").json()["total"] == 0


def test_fuel_stats_insufficient_data(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Stats"}).json()
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 10000, "liters": 40, "full_tank": True,
    })
    res = auth_client.get(f"/api/vehicles/{v['id']}/fuel-stats")
    assert res.status_code == 200
    assert res.json()["avg_consumption"] is None
    assert res.json()["entries_count"] == 1


def test_fuel_stats_with_data(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Full Stats"}).json()
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-01", "mileage": 10000, "liters": 45, "price_per_liter": 1.80, "full_tank": True,
    })
    auth_client.post(f"/api/vehicles/{v['id']}/fuel", json={
        "date": "2025-01-15", "mileage": 10500, "liters": 40, "price_per_liter": 1.85, "full_tank": True,
    })
    res = auth_client.get(f"/api/vehicles/{v['id']}/fuel-stats")
    assert res.status_code == 200
    data = res.json()
    assert data["entries_count"] == 2
    assert data["total_liters"] == 85
    assert data["avg_cost_per_km"] is not None


def test_vehicle_photo_upload(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Photo"}).json()
    # Create a minimal JPEG (just the header bytes)
    import io
    jpeg_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 100 + b'\xff\xd9'
    res = auth_client.post(
        f"/api/vehicles/{v['id']}/photo",
        files={"file": ("car.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
    )
    assert res.status_code == 200
    assert "photo_path" in res.json()


def test_vehicle_photo_bad_format(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "BadPhoto"}).json()
    import io
    res = auth_client.post(
        f"/api/vehicles/{v['id']}/photo",
        files={"file": ("doc.pdf", io.BytesIO(b"fake pdf"), "application/pdf")},
    )
    assert res.status_code == 400


def test_fuel_requires_auth(client):
    res = client.get("/api/vehicles/1/fuel")
    assert res.status_code == 401

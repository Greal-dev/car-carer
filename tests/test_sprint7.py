"""Tests for Sprint 7: reminders, warranties."""


def _create_vehicle_with_maintenance(auth_client):
    """Helper: create vehicle + maintenance event with items."""
    v = auth_client.post("/api/vehicles", json={"name": "Remind"}).json()
    # We need a maintenance event with items to attach a warranty
    # Upload a fake document first won't work without Gemini, so we check endpoints directly
    return v


def test_reminders_empty(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "Empty"}).json()
    res = auth_client.get(f"/api/vehicles/{v['id']}/reminders")
    assert res.status_code == 200
    data = res.json()
    assert "reminders" in data
    assert "counts" in data
    assert data["counts"]["total"] >= 0


def test_reminders_requires_auth(client):
    res = client.get("/api/vehicles/1/reminders")
    assert res.status_code == 401


def test_warranty_crud(auth_client, db_session):
    """Test warranty create, list, delete using direct DB insertion for maintenance item."""
    from app.models import Vehicle, MaintenanceEvent, MaintenanceItem
    from datetime import date

    v = auth_client.post("/api/vehicles", json={"name": "WarrantyTest"}).json()
    vid = v["id"]

    # Insert maintenance event + item directly in DB
    event = MaintenanceEvent(vehicle_id=vid, date=date(2025, 1, 15), mileage=50000,
                             garage_name="Garage Test", total_cost=350.0, event_type="invoice")
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    item = MaintenanceItem(event_id=event.id, description="Plaquettes de frein AV",
                           category="freinage", total_price=180.0)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    # Create warranty
    res = auth_client.post(f"/api/vehicles/{vid}/warranties", json={
        "item_id": item.id, "description": "Garantie plaquettes",
        "duration_months": 24, "start_date": "2025-01-15",
    })
    assert res.status_code == 201
    w = res.json()
    assert w["description"] == "Garantie plaquettes"
    assert w["end_date"] == "2027-01-15"
    assert w["vehicle_id"] == vid

    # List warranties
    res = auth_client.get(f"/api/vehicles/{vid}/warranties")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # Delete warranty
    res = auth_client.delete(f"/api/vehicles/{vid}/warranties/{w['id']}")
    assert res.status_code == 204
    assert len(auth_client.get(f"/api/vehicles/{vid}/warranties").json()) == 0


def test_warranty_wrong_item(auth_client):
    v = auth_client.post("/api/vehicles", json={"name": "BadItem"}).json()
    res = auth_client.post(f"/api/vehicles/{v['id']}/warranties", json={
        "item_id": 99999, "description": "Test", "start_date": "2025-01-01",
    })
    assert res.status_code == 404


def test_reminders_with_warranty(auth_client, db_session):
    """Test that expiring warranty shows in reminders."""
    from app.models import MaintenanceEvent, MaintenanceItem, Warranty
    from datetime import date, timedelta

    v = auth_client.post("/api/vehicles", json={"name": "WRemind"}).json()
    vid = v["id"]

    event = MaintenanceEvent(vehicle_id=vid, date=date(2024, 1, 1), mileage=30000,
                             total_cost=200.0, event_type="invoice")
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    item = MaintenanceItem(event_id=event.id, description="Batterie", category="electricite", total_price=120.0)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    # Warranty expiring in 1 month
    soon = date.today() + timedelta(days=20)
    w = Warranty(item_id=item.id, vehicle_id=vid, description="Garantie batterie",
                 duration_months=24, start_date=date(2024, 1, 1), end_date=soon)
    db_session.add(w)
    db_session.commit()

    res = auth_client.get(f"/api/vehicles/{vid}/reminders")
    assert res.status_code == 200
    data = res.json()
    warranty_reminders = [r for r in data["reminders"] if r["source"] == "warranty"]
    assert len(warranty_reminders) >= 1
    assert "batterie" in warranty_reminders[0]["title"].lower()


def test_warranties_requires_auth(client):
    res = client.get("/api/vehicles/1/warranties")
    assert res.status_code == 401

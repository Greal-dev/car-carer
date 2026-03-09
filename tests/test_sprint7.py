"""Tests for Sprint 7: reminders."""


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

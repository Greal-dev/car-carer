"""Tests for Sprint 5 features: dashboard."""


def test_dashboard(auth_client):
    auth_client.post("/api/vehicles", json={"name": "V1"})
    auth_client.post("/api/vehicles", json={"name": "V2"})
    res = auth_client.get("/api/vehicles/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["vehicle_count"] == 2
    assert len(data["vehicles"]) == 2
    assert "avg_health_score" in data["summary"]


def test_dashboard_requires_auth(client):
    res = client.get("/api/vehicles/dashboard")
    assert res.status_code == 401

"""Tests for vehicle sharing / access endpoints."""

import pytest


def _create_vehicle(auth_client):
    res = auth_client.post("/api/vehicles", json={"name": "SharedCar"})
    assert res.status_code == 201
    return res.json()["id"]


def _register_second_user_and_relogin(auth_client):
    """Register a second user, then re-login as user1. Returns user2's email."""
    res = auth_client.post("/api/auth/register", json={
        "email": "user2@test.com",
        "password": "pass456",
    })
    assert res.status_code == 200

    login_res = auth_client.post("/api/auth/login", json={
        "email": "test@test.com",
        "password": "test123",
    })
    assert login_res.status_code == 200

    return "user2@test.com"


def test_share_vehicle(auth_client):
    vid = _create_vehicle(auth_client)
    user2_email = _register_second_user_and_relogin(auth_client)

    res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": user2_email,
        "role": "viewer",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["vehicle_id"] == vid
    assert data["role"] == "viewer"
    assert data["user_email"] == user2_email
    assert "id" in data
    assert "created_at" in data
    assert data["granted_by_user_id"] is not None


def test_list_access(auth_client):
    vid = _create_vehicle(auth_client)
    user2_email = _register_second_user_and_relogin(auth_client)

    auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": user2_email,
        "role": "editor",
    })

    res = auth_client.get(f"/api/vehicles/{vid}/access")
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) == 1
    assert entries[0]["user_email"] == user2_email
    assert entries[0]["role"] == "editor"


def test_revoke_access(auth_client):
    vid = _create_vehicle(auth_client)
    user2_email = _register_second_user_and_relogin(auth_client)

    share_res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": user2_email,
        "role": "viewer",
    })
    assert share_res.status_code == 201
    access_id = share_res.json()["id"]

    res = auth_client.delete(f"/api/vehicles/{vid}/access/{access_id}")
    assert res.status_code == 204

    list_res = auth_client.get(f"/api/vehicles/{vid}/access")
    assert len(list_res.json()) == 0


def test_shared_with_me(auth_client):
    """Test that shared-with-me shows vehicles shared with user2."""
    vid = _create_vehicle(auth_client)
    user2_email = _register_second_user_and_relogin(auth_client)

    share_res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": user2_email,
        "role": "viewer",
    })
    assert share_res.status_code == 201

    # Login as user2
    auth_client.post("/api/auth/login", json={
        "email": "user2@test.com",
        "password": "pass456",
    })

    res = auth_client.get("/api/vehicles/shared-with-me")
    assert res.status_code == 200
    shared = res.json()
    assert len(shared) == 1
    assert shared[0]["vehicle_id"] == vid
    assert shared[0]["role"] == "viewer"


def test_share_requires_owner(auth_client):
    """A non-owner cannot share a vehicle."""
    vid = _create_vehicle(auth_client)
    user2_email = _register_second_user_and_relogin(auth_client)

    share_res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": user2_email,
        "role": "viewer",
    })
    assert share_res.status_code == 201

    # Register user3
    auth_client.post("/api/auth/register", json={
        "email": "user3@test.com",
        "password": "pass789",
    })

    # Login as user2 (viewer, not owner)
    auth_client.post("/api/auth/login", json={
        "email": "user2@test.com",
        "password": "pass456",
    })

    # user2 tries to share with user3 — should fail 403
    res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": "user3@test.com",
        "role": "viewer",
    })
    assert res.status_code == 403


def test_share_requires_auth(client):
    res = client.post("/api/vehicles/1/share", json={
        "email": "someone@test.com",
        "role": "viewer",
    })
    assert res.status_code == 401


def test_share_duplicate(auth_client):
    """Sharing twice with the same user should return 409."""
    vid = _create_vehicle(auth_client)
    user2_email = _register_second_user_and_relogin(auth_client)

    first_res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": user2_email,
        "role": "viewer",
    })
    assert first_res.status_code == 201

    res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": user2_email,
        "role": "editor",
    })
    assert res.status_code == 409


def test_share_with_self(auth_client):
    """Cannot share a vehicle with yourself."""
    vid = _create_vehicle(auth_client)

    res = auth_client.post(f"/api/vehicles/{vid}/share", json={
        "email": "test@test.com",
        "role": "viewer",
    })
    assert res.status_code == 400

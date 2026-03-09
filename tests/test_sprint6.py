"""Tests for Sprint 6: vehicle photo."""


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

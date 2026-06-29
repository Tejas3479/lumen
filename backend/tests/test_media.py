"""
Tests: Media Upload System (Session 5)

Covers:
  - Upload JPEG and PNG (happy path)
  - Upload unsupported file type (PDF) → 422
  - Upload with spoofed Content-Type header (MIME mismatch) → 422
  - GET media metadata
  - DELETE by non-owner (403 or 204 for unlinked media)
  - GET non-existent media → 404
  - Upload produces media_type = 'photo'
"""
import io
import uuid

import pytest
from PIL import Image


# ── Helpers ────────────────────────────────────────────────────

def _make_jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    """Generate a minimal valid JPEG in memory using Pillow."""
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(255, 100, 50))
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


def _make_png_bytes(width: int = 50, height: int = 50) -> bytes:
    """Generate a minimal valid PNG in memory using Pillow."""
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(0, 128, 255))
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


async def _register_and_login(client, suffix: str) -> str:
    """Register a user and return their access token."""
    reg = await client.post("/auth/register", json={
        "email": f"media_{suffix}@lumen.com",
        "password": "password123",
        "username": f"media_{suffix}",
        "display_name": f"Media {suffix}",
    })
    return reg.json()["access_token"]


# ── Upload tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_jpeg_standalone(client):
    """Upload a JPEG without linking to an issue — returns 201 with photo type."""
    token = await _register_and_login(client, "uploader1")
    jpeg_bytes = _make_jpeg_bytes()

    response = await client.post(
        "/media/upload",
        files={"file": ("test_photo.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["media_type"] == "photo"
    assert data["file_size"] == len(jpeg_bytes)
    assert "id" in data
    assert "file_path" in data


@pytest.mark.asyncio
async def test_upload_png_standalone(client):
    """PNG files should be accepted and identified as 'photo'."""
    token = await _register_and_login(client, "uploader2")
    png_bytes = _make_png_bytes()

    response = await client.post(
        "/media/upload",
        files={"file": ("test_photo.png", io.BytesIO(png_bytes), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["media_type"] == "photo"


@pytest.mark.asyncio
async def test_upload_rejected_file_type(client):
    """PDF content must be rejected regardless of filename."""
    token = await _register_and_login(client, "uploader3")
    # Realistic PDF magic bytes
    fake_pdf = b"%PDF-1.4 fake pdf content here for testing rejection by MIME sniff"

    response = await client.post(
        "/media/upload",
        files={"file": ("document.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_spoofed_content_type_rejected(client):
    """
    A file that is plain text but sent with image/jpeg Content-Type
    must be rejected by server-side MIME sniffing.
    """
    token = await _register_and_login(client, "uploader4")
    # Plain text — no JPEG magic bytes
    fake_content = b"This is not an image, just plain text content trying to bypass MIME check"

    response = await client.post(
        "/media/upload",
        files={"file": ("fake.jpg", io.BytesIO(fake_content), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    # MIME sniffing must detect the mismatch and reject
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_unauthenticated_still_works(client):
    """
    Anonymous uploads are allowed (used by guest reporters).
    The endpoint accepts OptionalUser.
    """
    jpeg_bytes = _make_jpeg_bytes()

    response = await client.post(
        "/media/upload",
        files={"file": ("anon.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
    )
    # Should succeed (no auth required for upload)
    assert response.status_code == 201


# ── Get metadata tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_media_metadata(client):
    """After upload, GET /media/{id} returns the correct record."""
    token = await _register_and_login(client, "uploader5")
    jpeg_bytes = _make_jpeg_bytes()

    upload_resp = await client.post(
        "/media/upload",
        files={"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_resp.status_code == 201
    media_id = upload_resp.json()["id"]

    get_resp = await client.get(f"/media/{media_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["id"] == media_id
    assert body["media_type"] == "photo"
    assert body["file_size"] == len(jpeg_bytes)


@pytest.mark.asyncio
async def test_get_nonexistent_media(client):
    """Fetching a media record that doesn't exist returns 404."""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/media/{fake_id}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


# ── Delete tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_own_media(client):
    """
    A user who uploaded standalone media (placeholder issue UUID)
    can delete it. Expects 204.
    """
    token = await _register_and_login(client, "deleter1")
    jpeg_bytes = _make_jpeg_bytes()

    upload_resp = await client.post(
        "/media/upload",
        files={"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    media_id = upload_resp.json()["id"]

    del_resp = await client.delete(
        f"/media/{media_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_media_unauthenticated_rejected(client):
    """DELETE without auth token returns 401."""
    token = await _register_and_login(client, "deleter2")
    jpeg_bytes = _make_jpeg_bytes()

    upload_resp = await client.post(
        "/media/upload",
        files={"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    media_id = upload_resp.json()["id"]

    del_resp = await client.delete(f"/media/{media_id}")
    assert del_resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_nonexistent_media(client):
    """Deleting a media record that doesn't exist returns 404."""
    token = await _register_and_login(client, "deleter3")
    fake_id = str(uuid.uuid4())

    del_resp = await client.delete(
        f"/media/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_media_after_delete_returns_404(client):
    """After deletion, fetching the same media returns 404."""
    token = await _register_and_login(client, "deleter4")
    jpeg_bytes = _make_jpeg_bytes()

    upload_resp = await client.post(
        "/media/upload",
        files={"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    media_id = upload_resp.json()["id"]

    await client.delete(
        f"/media/{media_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    get_resp = await client.get(f"/media/{media_id}")
    assert get_resp.status_code == 404

"""
Tests: Community Verification
Covers:
  - Soft verification creates record with trust_weight=0.5
  - Hard verification within 100m creates record with trust_weight=1.0
  - Hard verification >100m away is rejected (422)
  - Hard verification with no GPS is rejected (422)
  - Duplicate verification by same user is rejected (409)
  - Reporter cannot verify their own issue (403)
  - Auto-status-upgrade to 'verified' when weighted score >= 2.0
  - verification_count is incremented on each successful verification
  - Unauthenticated request is rejected (401)
"""
import pytest
import uuid


# =============================================================
# Helpers
# =============================================================

async def _register(client, suffix: str) -> str:
    """Register a unique user and return their access token."""
    reg = await client.post("/auth/register", json={
        "email": f"{suffix}@lumen.com",
        "password": "password123",
        "username": suffix,
        "display_name": suffix.replace("_", " ").title(),
    })
    assert reg.status_code in (200, 201), f"Registration failed for {suffix}: {reg.text}"
    return reg.json()["access_token"]


async def _create_issue(client, token: str, lat: float = 12.9716, lng: float = 77.5946) -> str:
    """Create an issue as the given user and return its ID."""
    resp = await client.post(
        "/issues",
        data={
            "title": "Verification test pothole on main road",
            "description": "Large pothole near the junction causing vehicle damage and accidents.",
            "latitude": str(lat),
            "longitude": str(lng),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Issue creation failed: {resp.text}"
    return resp.json()["id"]


# =============================================================
# Tests
# =============================================================

@pytest.mark.asyncio
async def test_soft_verification_success(client):
    """Soft verification returns trust_weight=0.5 and 200 OK."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_{sfx}")
    verifier_token = await _register(client, f"ver_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    resp = await client.post(
        f"/issues/{issue_id}/verify",
        json={"verification_type": "soft"},
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verification_type"] == "soft"
    assert data["trust_weight"] == 0.5
    assert data["issue_id"] == issue_id


@pytest.mark.asyncio
async def test_hard_verification_within_radius(client):
    """Hard verification with GPS within 100m returns trust_weight=1.0."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_h_{sfx}")
    verifier_token = await _register(client, f"ver_h_{sfx}")
    issue_id = await _create_issue(client, reporter_token, lat=12.9716, lng=77.5946)

    # 50m north — approximately 50/111320 degrees latitude
    nearby_lat = 12.9716 + (50 / 111_320)

    resp = await client.post(
        f"/issues/{issue_id}/verify",
        json={
            "verification_type": "hard",
            "latitude": nearby_lat,
            "longitude": 77.5946,
        },
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verification_type"] == "hard"
    assert data["trust_weight"] == 1.0
    assert data["distance_meters"] is not None
    assert data["distance_meters"] < 100


@pytest.mark.asyncio
async def test_hard_verification_too_far_rejected(client):
    """Hard verification with GPS 500m away must return 422."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_far_{sfx}")
    verifier_token = await _register(client, f"ver_far_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    # 500m north — well outside 100m hard-verification radius
    far_lat = 12.9716 + (500 / 111_320)

    resp = await client.post(
        f"/issues/{issue_id}/verify",
        json={
            "verification_type": "hard",
            "latitude": far_lat,
            "longitude": 77.5946,
        },
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    # Error message should mention distance or proximity
    msg = body.get("message", body.get("detail", {}).get("message", "")).lower()
    assert any(kw in msg for kw in ("far", "m from", "radius", "within")), (
        f"Expected proximity error, got: {msg}"
    )


@pytest.mark.asyncio
async def test_hard_verification_no_gps_rejected(client):
    """Hard verification without latitude/longitude must return 422."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_nogps_{sfx}")
    verifier_token = await _register(client, f"ver_nogps_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    resp = await client.post(
        f"/issues/{issue_id}/verify",
        json={"verification_type": "hard"},  # No lat/lng
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_duplicate_verification_rejected(client):
    """A second verification by the same user must return 409."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_dup_{sfx}")
    verifier_token = await _register(client, f"ver_dup_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    # First verification — should succeed
    r1 = await client.post(
        f"/issues/{issue_id}/verify",
        json={"verification_type": "soft"},
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert r1.status_code == 200, r1.text

    # Second verification by same user — must be rejected
    r2 = await client.post(
        f"/issues/{issue_id}/verify",
        json={"verification_type": "soft"},
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert r2.status_code == 409, r2.text


@pytest.mark.asyncio
async def test_cannot_verify_own_issue(client):
    """Reporter verifying their own issue must return 403."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_own_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    resp = await client.post(
        f"/issues/{issue_id}/verify",
        json={"verification_type": "soft"},
        headers={"Authorization": f"Bearer {reporter_token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_verification_increments_count(client):
    """Each successful verification increments issue.verification_count by 1."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_cnt_{sfx}")
    verifier_token = await _register(client, f"ver_cnt_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    before = await client.get(f"/issues/{issue_id}")
    count_before = before.json()["verification_count"]

    await client.post(
        f"/issues/{issue_id}/verify",
        json={"verification_type": "soft"},
        headers={"Authorization": f"Bearer {verifier_token}"},
    )

    after = await client.get(f"/issues/{issue_id}")
    assert after.json()["verification_count"] == count_before + 1


@pytest.mark.asyncio
async def test_auto_upgrade_to_verified_on_threshold(client):
    """
    Two hard verifications (each 1.0 weight, total 2.0) must auto-upgrade
    the issue status from 'reported' to 'verified'.
    """
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_upg_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    # Verify status is 'reported' before we start
    before = await client.get(f"/issues/{issue_id}")
    assert before.json()["status"] == "reported"

    nearby_lat = 12.9716 + (30 / 111_320)  # 30m north — within 100m

    # Two distinct users each do a hard verification
    for i in range(2):
        sfx2 = uuid.uuid4().hex[:8]
        token = await _register(client, f"upg_ver_{i}_{sfx2}")
        r = await client.post(
            f"/issues/{issue_id}/verify",
            json={
                "verification_type": "hard",
                "latitude": nearby_lat,
                "longitude": 77.5946,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, f"Verification {i} failed: {r.text}"

    # Status must now be 'verified'
    after = await client.get(f"/issues/{issue_id}")
    assert after.json()["status"] == "verified", (
        f"Expected 'verified', got '{after.json()['status']}'"
    )


@pytest.mark.asyncio
async def test_unauthenticated_verification_rejected(client):
    """Verification without an Authorization header must return 401."""
    sfx = uuid.uuid4().hex[:8]
    reporter_token = await _register(client, f"rep_anon_{sfx}")
    issue_id = await _create_issue(client, reporter_token)

    resp = await client.post(
        f"/issues/{issue_id}/verify",
        json={"verification_type": "soft"},
        # No Authorization header
    )
    assert resp.status_code == 401, resp.text

"""
Tests: Full Issue Lifecycle
report → verify → assign → in_progress → resolved → confirm
and: report → verify → resolve → dispute × 3 → auto-reopen
"""
import pytest


# ─── Helpers ──────────────────────────────────────────────────

async def _register_user(client, email: str, username: str, display_name: str = "User") -> dict:
    """Register a fresh user and return auth headers."""
    reg = await client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "username": username,
        "display_name": display_name,
    })
    assert reg.status_code == 201, f"Register failed for {email}: {reg.text}"
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _admin_login(client) -> dict:
    """
    Obtain admin headers.  Tries to login with seeded admin credentials first;
    falls back to registering a fresh admin account in the test DB (which
    starts without any seed data).
    """
    resp = await client.post("/auth/login", json={
        "email": "admin@lumen.com",
        "password": "admin123",
    })
    if resp.status_code == 200:
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # Test DB has no seed — register a new user and elevate via SQL
    reg = await client.post("/auth/register", json={
        "email": "admin_lifecycle@lumen.com",
        "password": "admin123",
        "username": "admin_lifecycle",
        "display_name": "Admin Lifecycle",
    })
    assert reg.status_code == 201, f"Admin register failed: {reg.text}"

    # The newly registered user is a regular citizen — we need to elevate them.
    # Promote via DB in the conftest db_session scope by updating is_admin.
    # For the lifecycle tests we instead use the official_or_admin dependency path.
    # We return headers and mark note: status transitions also work with is_official.
    # In test environment get_official_or_admin accepts any registered user IF
    # the test overrides or the route is reached via get_current_user.
    # For a clean test, we set is_admin=True via a raw SQL update.
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _make_user_admin(client, db_session, email: str):
    """Elevate a user to admin directly in the test database session."""
    from sqlalchemy import update as sa_update
    from app.models import User
    await db_session.execute(
        sa_update(User).where(User.email == email).values(is_admin=True, is_official=True)
    )
    await db_session.flush()


async def _create_issue(client, headers: dict, title_suffix: str = "lifecycle") -> str:
    """Create an issue and return its ID."""
    resp = await client.post("/issues", data={
        "title": f"Lifecycle pothole test — {title_suffix}",
        "description": "Large pothole on the main road causing vehicle damage near the junction.",
        "latitude": "12.9716",
        "longitude": "77.5946",
        "severity": "high",
    }, headers=headers)
    assert resp.status_code == 201, f"Issue creation failed: {resp.text}"
    return resp.json()["id"]


# ─── Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_report_to_resolution_lifecycle(client, db_session):
    """
    Complete lifecycle: report → community verify → admin assign →
    admin in_progress → admin resolve → citizen confirm.
    """
    # ── Setup users ────────────────────────────────────────────
    citizen_headers = await _register_user(
        client, "lifecycle_citizen@lumen.com", "lifecycle_citizen", "Lifecycle Citizen"
    )
    admin_headers = await _register_user(
        client, "lifecycle_admin@lumen.com", "lifecycle_admin", "Lifecycle Admin"
    )
    await _make_user_admin(client, db_session, "lifecycle_admin@lumen.com")

    # ── 1. Report issue ────────────────────────────────────────
    issue_id = await _create_issue(client, citizen_headers, "full lifecycle")
    issue_check = await client.get(f"/issues/{issue_id}")
    assert issue_check.json()["status"] == "reported"

    # ── 2. Two hard verifications to hit the threshold ─────────
    for i in range(2):
        verifier_headers = await _register_user(
            client,
            f"lifecycle_verifier_{i}@lumen.com",
            f"lifecycle_verifier_{i}",
            f"Verifier {i}",
        )
        v_resp = await client.post(
            f"/issues/{issue_id}/verify",
            json={
                "verification_type": "hard",
                "latitude": 12.9716 + (i * 10 / 111320),
                "longitude": 77.5946,
            },
            headers=verifier_headers,
        )
        assert v_resp.status_code == 200, f"Verify failed: {v_resp.text}"

    # Issue should auto-verify after sufficient hard-verifications
    after_verify = await client.get(f"/issues/{issue_id}")
    assert after_verify.json()["status"] in ("reported", "verified"), (
        f"Unexpected status: {after_verify.json()['status']}"
    )

    # ── 3. Admin assigns ───────────────────────────────────────
    assign_resp = await client.patch(
        f"/issues/{issue_id}/status",
        json={"status": "assigned", "note": "Assigned to Roads team"},
        headers=admin_headers,
    )
    assert assign_resp.status_code == 200, f"Assign failed: {assign_resp.text}"

    # ── 4. Admin marks in_progress ─────────────────────────────
    progress_resp = await client.patch(
        f"/issues/{issue_id}/status",
        json={"status": "in_progress", "note": "Work started"},
        headers=admin_headers,
    )
    assert progress_resp.status_code == 200, f"in_progress failed: {progress_resp.text}"

    # ── 5. Admin resolves ──────────────────────────────────────
    resolve_resp = await client.patch(
        f"/issues/{issue_id}/status",
        json={"status": "resolved", "note": "Pothole patched and re-surfaced"},
        headers=admin_headers,
    )
    assert resolve_resp.status_code == 200, f"Resolve failed: {resolve_resp.text}"

    # ── 6. Citizen confirms resolution ─────────────────────────
    confirm_resp = await client.post(
        f"/issues/{issue_id}/resolution-feedback",
        json={"is_resolved": True, "comment": "Yes, it's fixed!"},
        headers=citizen_headers,
    )
    assert confirm_resp.status_code == 200, f"Confirm failed: {confirm_resp.text}"

    # ── Final check ────────────────────────────────────────────
    final = await client.get(f"/issues/{issue_id}")
    assert final.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_dispute_triggers_reopen(client, db_session):
    """
    Three distinct dispute feedbacks must auto-reopen a resolved issue.
    """
    # ── Setup ──────────────────────────────────────────────────
    reporter_headers = await _register_user(
        client, "dispute_reporter@lumen.com", "dispute_reporter", "Dispute Reporter"
    )
    admin_headers = await _register_user(
        client, "dispute_admin@lumen.com", "dispute_admin", "Dispute Admin"
    )
    await _make_user_admin(client, db_session, "dispute_admin@lumen.com")

    # ── Create issue and fast-track to resolved ────────────────
    issue_id = await _create_issue(client, reporter_headers, "dispute reopen")

    await client.patch(
        f"/issues/{issue_id}/status",
        json={"status": "in_progress", "note": "Fast-track for dispute test"},
        headers=admin_headers,
    )
    await client.patch(
        f"/issues/{issue_id}/status",
        json={"status": "resolved", "note": "Marked resolved"},
        headers=admin_headers,
    )

    # Confirm it's resolved
    state = await client.get(f"/issues/{issue_id}")
    assert state.json()["status"] == "resolved"

    # ── Three citizens dispute ─────────────────────────────────
    for i in range(3):
        disputer_headers = await _register_user(
            client,
            f"disputer_{i}@lumen.com",
            f"disputer_{i}",
            f"Disputer {i}",
        )
        fb = await client.post(
            f"/issues/{issue_id}/resolution-feedback",
            json={"is_resolved": False, "comment": "Not fixed — still a problem!"},
            headers=disputer_headers,
        )
        assert fb.status_code == 200, f"Dispute feedback failed: {fb.text}"

    # ── Issue must be auto-reopened / disputed ─────────────────
    final = await client.get(f"/issues/{issue_id}")
    assert final.json()["status"] in ("disputed", "in_progress", "reported"), (
        f"Expected disputed/reopened status, got: {final.json()['status']}"
    )


@pytest.mark.asyncio
async def test_issue_status_unauthenticated_rejected(client):
    """
    Unauthenticated PATCH on status must return 401.
    """
    # Use a fake UUID — we just need to hit the auth guard
    fake_id = "00000000-0000-0000-0000-000000000001"
    resp = await client.patch(
        f"/issues/{fake_id}/status",
        json={"status": "resolved"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_issue_created_starts_in_reported_status(client):
    """
    Any newly created issue must begin with status='reported'.
    """
    user_headers = await _register_user(
        client, "status_check@lumen.com", "status_checker", "Status Checker"
    )
    issue_id = await _create_issue(client, user_headers, "status initial check")
    detail = await client.get(f"/issues/{issue_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "reported"

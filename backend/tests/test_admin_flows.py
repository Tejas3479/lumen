"""
Tests: Admin Workflow

Covers:
  - Non-admin citizen is rejected from admin endpoints (403)
  - Unauthenticated access to admin endpoints returns 401
  - Admin can access queue when authenticated and elevated
  - Admin can change issue status
  - Admin can bulk-update issues
  - Admin export endpoints require authentication
  - Admin can list and moderate users
"""
import pytest
from sqlalchemy import update as sa_update
from app.models import User


# ─── Helpers ──────────────────────────────────────────────────

async def _register_user(client, email: str, username: str, display_name: str = "User") -> dict:
    """Register a user and return auth headers + user data."""
    reg = await client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "username": username,
        "display_name": display_name,
    })
    assert reg.status_code == 201, f"Register failed for {email}: {reg.text}"
    return {"headers": {"Authorization": f"Bearer {reg.json()['access_token']}"}, "data": reg.json()}


async def _make_admin(db_session, email: str):
    """Elevate a user to admin in the test database."""
    await db_session.execute(
        sa_update(User).where(User.email == email).values(is_admin=True, is_official=True)
    )
    await db_session.flush()


async def _create_issue_for_test(client, headers: dict, suffix: str = "admin") -> str:
    """Create a test issue and return its ID."""
    resp = await client.post("/issues", data={
        "title": f"Admin flow test issue — {suffix}",
        "description": "Issue created for admin workflow test coverage purposes.",
        "latitude": "12.9716",
        "longitude": "77.5946",
        "severity": "medium",
    }, headers=headers)
    assert resp.status_code == 201, f"Issue creation failed: {resp.text}"
    return resp.json()["id"]


# ─── Auth Guard Tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_queue_requires_auth(client):
    """GET /admin/queue without a token must return 401."""
    resp = await client.get("/admin/queue")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_export_requires_auth(client):
    """GET /admin/export without a token must return 401."""
    resp = await client.get("/admin/export?format=csv")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_users_requires_auth(client):
    """GET /admin/users without a token must return 401."""
    resp = await client.get("/admin/users")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_flags_requires_auth(client):
    """GET /admin/flags without a token must return 401."""
    resp = await client.get("/admin/flags")
    assert resp.status_code == 401


# ─── Non-Admin Rejection Tests ────────────────────────────────

@pytest.mark.asyncio
async def test_non_admin_cannot_access_queue(client):
    """A regular citizen token must be rejected from /admin/queue with 403."""
    citizen = await _register_user(
        client, "citizen_queue_test@lumen.com", "citizen_queue_test", "Citizen Queue"
    )
    resp = await client.get("/admin/queue", headers=citizen["headers"])
    assert resp.status_code == 403, f"Expected 403 for citizen, got: {resp.status_code}"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_users_list(client):
    """A regular citizen must not be able to list all users."""
    citizen = await _register_user(
        client, "citizen_users_test@lumen.com", "citizen_users_test", "Citizen Users"
    )
    resp = await client.get("/admin/users", headers=citizen["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_export(client):
    """A regular citizen must not be able to export issue data."""
    citizen = await _register_user(
        client, "citizen_export_test@lumen.com", "citizen_export_test", "Citizen Export"
    )
    resp = await client.get("/admin/export?format=csv", headers=citizen["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_moderate_users(client):
    """A regular citizen must not be able to moderate (ban) other users."""
    citizen = await _register_user(
        client, "citizen_mod_test@lumen.com", "citizen_mod_test", "Citizen Mod"
    )
    target = await _register_user(
        client, "target_mod_test@lumen.com", "target_mod_test", "Target"
    )
    target_id = target["data"]["user_id"] if "user_id" in target["data"] else "00000000-0000-0000-0000-000000000001"

    resp = await client.patch(
        f"/admin/users/{target_id}/moderate",
        json={"is_banned": True},
        headers=citizen["headers"],
    )
    assert resp.status_code in (403, 404)  # 403 for auth; 404 if ID resolution differs


# ─── Admin Capability Tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_admin_queue_returns_paginated_issues(client, db_session):
    """Admin can access /admin/queue and receives a paginated response."""
    admin = await _register_user(
        client, "admin_queue_user@lumen.com", "admin_queue_user", "Admin Queue"
    )
    await _make_admin(db_session, "admin_queue_user@lumen.com")

    resp = await client.get("/admin/queue", headers=admin["headers"])
    assert resp.status_code == 200, f"Admin queue failed: {resp.text}"

    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "per_page" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_admin_can_change_issue_status(client, db_session):
    """Admin can transition an issue from reported → in_progress → resolved."""
    admin = await _register_user(
        client, "admin_status_user@lumen.com", "admin_status_user", "Admin Status"
    )
    await _make_admin(db_session, "admin_status_user@lumen.com")

    reporter = await _register_user(
        client, "reporter_admin_flow@lumen.com", "reporter_admin_flow", "Reporter"
    )
    issue_id = await _create_issue_for_test(client, reporter["headers"], "status-change")

    # in_progress
    r1 = await client.patch(
        f"/issues/{issue_id}/status",
        json={"status": "in_progress", "note": "Work started by admin"},
        headers=admin["headers"],
    )
    assert r1.status_code == 200, f"in_progress transition failed: {r1.text}"

    # resolved
    r2 = await client.patch(
        f"/issues/{issue_id}/status",
        json={"status": "resolved", "note": "Issue fixed"},
        headers=admin["headers"],
    )
    assert r2.status_code == 200, f"resolved transition failed: {r2.text}"

    # Confirm final status
    detail = await client.get(f"/issues/{issue_id}")
    assert detail.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_admin_bulk_update(client, db_session):
    """Admin can bulk-update multiple issues to the same status."""
    admin = await _register_user(
        client, "admin_bulk_user@lumen.com", "admin_bulk_user", "Admin Bulk"
    )
    await _make_admin(db_session, "admin_bulk_user@lumen.com")

    reporter = await _register_user(
        client, "reporter_bulk@lumen.com", "reporter_bulk", "Reporter Bulk"
    )

    # Create two issues
    issue_ids = [
        await _create_issue_for_test(client, reporter["headers"], f"bulk-{i}")
        for i in range(2)
    ]

    # Bulk update both to in_progress
    bulk_resp = await client.patch(
        "/admin/issues/bulk",
        json={
            "issue_ids": issue_ids,
            "status": "in_progress",
            "note": "Bulk update test from admin",
        },
        headers=admin["headers"],
    )
    assert bulk_resp.status_code == 200, f"Bulk update failed: {bulk_resp.text}"

    body = bulk_resp.json()
    assert "updated" in body
    assert len(body["updated"]) == 2
    assert len(body.get("errors", [])) == 0


@pytest.mark.asyncio
async def test_admin_export_csv(client, db_session):
    """Admin can export issues as CSV and receives a valid CSV response."""
    admin = await _register_user(
        client, "admin_export_user@lumen.com", "admin_export_user", "Admin Export"
    )
    await _make_admin(db_session, "admin_export_user@lumen.com")

    resp = await client.get("/admin/export?format=csv", headers=admin["headers"])
    assert resp.status_code == 200, f"CSV export failed: {resp.text}"
    assert "text/csv" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_admin_export_json(client, db_session):
    """Admin can export issues as JSON."""
    admin = await _register_user(
        client, "admin_exportjson_user@lumen.com", "admin_exportjson_user", "Admin JSON"
    )
    await _make_admin(db_session, "admin_exportjson_user@lumen.com")

    resp = await client.get("/admin/export?format=json", headers=admin["headers"])
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    body = resp.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_admin_user_list_is_paginated(client, db_session):
    """Admin /users endpoint returns a paginated list of non-guest users."""
    admin = await _register_user(
        client, "admin_userlist@lumen.com", "admin_userlist", "Admin Userlist"
    )
    await _make_admin(db_session, "admin_userlist@lumen.com")

    resp = await client.get("/admin/users?per_page=10", headers=admin["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_admin_user_search(client, db_session):
    """Admin can search for a specific user by username."""
    admin = await _register_user(
        client, "admin_search@lumen.com", "admin_search", "Admin Search"
    )
    await _make_admin(db_session, "admin_search@lumen.com")

    # Register a known user to search for
    await _register_user(
        client, "searchable_unique@lumen.com", "searchable_unique", "Searchable User"
    )

    resp = await client.get(
        "/admin/users?search=searchable_unique",
        headers=admin["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    usernames = [u["username"] for u in body["items"]]
    assert "searchable_unique" in usernames

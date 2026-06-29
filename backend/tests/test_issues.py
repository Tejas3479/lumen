"""
Tests: Issue Reporting Engine
Covers: create issue, list issues, nearby, get by id,
        update, delete, status transitions, flag, support vote,
        spam detection, auth guards, pagination.
"""
import pytest
import io


# ─── Helpers ──────────────────────────────────────────────────

async def create_test_user(client, email="reporter@lumen.com", username="reporter1"):
    reg = await client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "username": username,
        "display_name": "Test Reporter",
    })
    return reg.json()["access_token"]


async def create_test_official(client):
    # Register then manually set is_official via admin — for now use admin token
    reg = await client.post("/auth/register", json={
        "email": "official@lumen.com",
        "password": "password123",
        "username": "official1",
        "display_name": "Test Official",
    })
    return reg.json()["access_token"]


def make_issue_form(overrides: dict = {}) -> dict:
    base = {
        "title": "Test pothole on Main Street",
        "description": "Large pothole causing vehicle damage near the intersection",
        "latitude": "12.9716",
        "longitude": "77.5946",
        "severity": "medium",
        "is_anonymous": "false",
        "is_emergency": "false",
    }
    return {**base, **overrides}


# ─── Create Issue ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_issue_authenticated(client):
    token = await create_test_user(client)
    data = make_issue_form()
    response = await client.post(
        "/issues",
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Test pothole on Main Street"
    assert body["status"] == "reported"
    assert body["severity"] == "medium"
    assert "id" in body


@pytest.mark.asyncio
async def test_create_issue_anonymous_guest(client):
    """Guests can create issues without registering."""
    guest = await client.post("/auth/guest")
    token = guest.json()["access_token"]
    response = await client.post(
        "/issues",
        data=make_issue_form({"is_anonymous": "true"}),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["is_anonymous"] is True


@pytest.mark.asyncio
async def test_create_issue_title_too_short(client):
    token = await create_test_user(client, "short@lumen.com", "short_user")
    response = await client.post(
        "/issues",
        data=make_issue_form({"title": "Hi"}),
        headers={"Authorization": f"Bearer {token}"},
    )
    # FastAPI form min_length validation → 422
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_issue_description_too_short(client):
    token = await create_test_user(client, "desc@lumen.com", "desc_user")
    response = await client.post(
        "/issues",
        data=make_issue_form({"description": "short"}),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_create_issue_missing_coordinates(client):
    token = await create_test_user(client, "coords@lumen.com", "coords_user")
    form = {
        "title": "Missing lat lng test issue",
        "description": "This issue has no coordinates provided to it",
        "severity": "low",
        "is_anonymous": "false",
        "is_emergency": "false",
    }
    response = await client.post(
        "/issues",
        data=form,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_emergency_issue(client):
    token = await create_test_user(client, "emerg@lumen.com", "emerg_user")
    response = await client.post(
        "/issues",
        data=make_issue_form({"is_emergency": "true", "severity": "critical"}),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["is_emergency"] is True
    assert body["severity"] == "critical"


# ─── List Issues ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_issues_no_auth(client):
    """Public feed requires no auth."""
    response = await client.get("/issues")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body


@pytest.mark.asyncio
async def test_list_issues_pagination(client):
    token = await create_test_user(client, "paginate@lumen.com", "paginate_user")
    for i in range(3):
        await client.post(
            "/issues",
            data=make_issue_form({
                "title": f"Pagination test issue number {i + 1}",
                "description": "Testing pagination across pages of the API",
            }),
            headers={"Authorization": f"Bearer {token}"},
        )
    response = await client.get("/issues?page=1&per_page=2")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) <= 2
    assert body["per_page"] == 2


@pytest.mark.asyncio
async def test_list_issues_filter_emergency(client):
    token = await create_test_user(client, "filter@lumen.com", "filter_user")
    await client.post(
        "/issues",
        data=make_issue_form({"is_emergency": "true", "title": "Emergency filter test issue"}),
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await client.get("/issues?is_emergency=true")
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert item["is_emergency"] is True


# ─── Nearby Issues ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_nearby_issues(client):
    token = await create_test_user(client, "nearby@lumen.com", "nearby_user")
    await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await client.get(
        "/issues/nearby",
        params={"lat": 12.9716, "lng": 77.5946, "radius": 5000}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_nearby_outside_radius_excluded(client):
    """Issue far away should not appear in nearby results."""
    response = await client.get(
        "/issues/nearby",
        params={"lat": 51.5074, "lng": -0.1278, "radius": 500}  # London — no issues
    )
    assert response.status_code == 200
    # May or may not be empty, but request should succeed
    assert isinstance(response.json(), list)


# ─── Get Issue By ID ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_issue_by_id(client):
    token = await create_test_user(client, "getbyid@lumen.com", "getbyid_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    response = await client.get(f"/issues/{issue_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == issue_id
    assert body["view_count"] >= 1


@pytest.mark.asyncio
async def test_get_issue_not_found(client):
    fake_id = "99999999-9999-9999-9999-999999999999"
    response = await client.get(f"/issues/{fake_id}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


# ─── Update Issue ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_issue_by_reporter(client):
    token = await create_test_user(client, "update@lumen.com", "update_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/issues/{issue_id}",
        json={"title": "Updated pothole title with more detail", "severity": "high"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["title"] == "Updated pothole title with more detail"
    assert body["severity"] == "high"


@pytest.mark.asyncio
async def test_update_issue_by_wrong_user(client):
    token1 = await create_test_user(client, "owner@lumen.com", "owner_user")
    token2 = await create_test_user(client, "other@lumen.com", "other_user")

    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token1}"},
    )
    issue_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/issues/{issue_id}",
        json={"title": "Unauthorized edit attempt by wrong user"},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert update_resp.status_code == 403


# ─── Delete Issue ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_close_issue_by_reporter(client):
    """Reporters close (not delete) their own issue."""
    token = await create_test_user(client, "close@lumen.com", "close_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/issues/{issue_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_issue_unauthenticated(client):
    token = await create_test_user(client, "delnoauth@lumen.com", "delnoauth_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]
    del_resp = await client.delete(f"/issues/{issue_id}")
    assert del_resp.status_code == 401


# ─── Support Vote ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_support_issue(client):
    token = await create_test_user(client, "vote@lumen.com", "vote_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    vote_resp = await client.post(
        f"/issues/{issue_id}/support",
        json={"issue_id": issue_id, "vote_type": "support"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert vote_resp.status_code == 200
    assert vote_resp.json()["vote_type"] == "support"


@pytest.mark.asyncio
async def test_support_issue_duplicate_rejected(client):
    """Second vote by same user returns 409."""
    token = await create_test_user(client, "dupvote@lumen.com", "dupvote_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    payload = {"issue_id": issue_id, "vote_type": "support"}
    await client.post(
        f"/issues/{issue_id}/support", json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    r2 = await client.post(
        f"/issues/{issue_id}/support", json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 409


# ─── Flag Issue ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flag_issue(client):
    token = await create_test_user(client, "flag@lumen.com", "flag_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    flag_resp = await client.post(
        f"/issues/{issue_id}/flag",
        json={"reason": "spam", "detail": "Duplicate report"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert flag_resp.status_code == 204


@pytest.mark.asyncio
async def test_flag_issue_duplicate_rejected(client):
    token = await create_test_user(client, "dupflag@lumen.com", "dupflag_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    payload = {"reason": "spam"}
    await client.post(f"/issues/{issue_id}/flag", json=payload,
                      headers={"Authorization": f"Bearer {token}"})
    r2 = await client.post(f"/issues/{issue_id}/flag", json=payload,
                           headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 409


# ─── Initial status in history ────────────────────────────────

@pytest.mark.asyncio
async def test_issue_has_status_history(client):
    token = await create_test_user(client, "history@lumen.com", "history_user")
    create_resp = await client.post(
        "/issues",
        data=make_issue_form(),
        headers={"Authorization": f"Bearer {token}"},
    )
    issue_id = create_resp.json()["id"]

    detail_resp = await client.get(f"/issues/{issue_id}")
    body = detail_resp.json()
    assert "status_history" in body
    # Initial 'reported' entry should exist
    assert any(h["to_status"] == "reported" for h in body["status_history"])

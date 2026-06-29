"""
Tests: Comments System
Session 11

Covers:
- create comment on an issue
- list comments for an issue
- edit own comment
- delete own comment (soft delete)
- cannot edit another user's comment (403)
- comment on a nonexistent issue (404)
- unauthenticated comment attempt (401)
"""
import pytest
import uuid


# ── Shared helper ─────────────────────────────────────────────────────────────

async def _create_issue_and_users(client):
    """
    Register two users and create one issue owned by user 1.
    Returns (token1, token2, issue_id).
    """
    reg1 = await client.post(
        "/auth/register",
        json={
            "email": "commenter1@lumen.com",
            "password": "password123",
            "username": "commenter1",
            "display_name": "Commenter 1",
        },
    )
    reg2 = await client.post(
        "/auth/register",
        json={
            "email": "commenter2@lumen.com",
            "password": "password123",
            "username": "commenter2",
            "display_name": "Commenter 2",
        },
    )
    token1 = reg1.json()["access_token"]
    token2 = reg2.json()["access_token"]

    issue_resp = await client.post(
        "/issues",
        data={
            "title": "Issue for comment testing purposes",
            "description": (
                "This issue is created specifically for testing comment functionality."
            ),
            "latitude": "12.9716",
            "longitude": "77.5946",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )
    return token1, token2, issue_resp.json()["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_comment(client):
    """POST /comments — authenticated user can create a comment."""
    token1, _, issue_id = await _create_issue_and_users(client)

    response = await client.post(
        "/comments",
        json={
            "issue_id": issue_id,
            "content": "I can confirm this issue exists near the junction.",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "I can confirm this issue exists near the junction."
    assert data["is_official"] is False
    assert "id" in data
    assert data["issue_id"] == issue_id


@pytest.mark.asyncio
async def test_list_comments(client):
    """GET /comments?issue_id= — returns a list of comments for the issue."""
    token1, _, issue_id = await _create_issue_and_users(client)

    # Create at least one comment so the list is non-empty
    await client.post(
        "/comments",
        json={
            "issue_id": issue_id,
            "content": "First community comment on this issue.",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )

    response = await client.get(f"/comments?issue_id={issue_id}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Official comments should sort before community ones
    assert "content" in data[0]


@pytest.mark.asyncio
async def test_edit_own_comment(client):
    """PATCH /comments/{id} — author can update the content of their comment."""
    token1, _, issue_id = await _create_issue_and_users(client)

    create_resp = await client.post(
        "/comments",
        json={
            "issue_id": issue_id,
            "content": "Original comment content here.",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )
    comment_id = create_resp.json()["id"]

    edit_resp = await client.patch(
        f"/comments/{comment_id}",
        json={"content": "Updated comment content with more details."},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert edit_resp.status_code == 200
    assert edit_resp.json()["content"] == "Updated comment content with more details."


@pytest.mark.asyncio
async def test_cannot_edit_others_comment(client):
    """PATCH /comments/{id} — user 2 cannot edit a comment owned by user 1."""
    token1, token2, issue_id = await _create_issue_and_users(client)

    create_resp = await client.post(
        "/comments",
        json={
            "issue_id": issue_id,
            "content": "Comment by user 1 that user 2 should not edit.",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )
    comment_id = create_resp.json()["id"]

    edit_resp = await client.patch(
        f"/comments/{comment_id}",
        json={"content": "User 2 trying to change user 1 comment."},
        headers={"Authorization": f"Bearer {token2}"},
    )

    assert edit_resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_own_comment(client):
    """DELETE /comments/{id} — author can soft-delete their own comment."""
    token1, _, issue_id = await _create_issue_and_users(client)

    create_resp = await client.post(
        "/comments",
        json={
            "issue_id": issue_id,
            "content": "Comment to be deleted by its author.",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )
    comment_id = create_resp.json()["id"]

    delete_resp = await client.delete(
        f"/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert delete_resp.status_code == 204

    # Verify the comment no longer appears in the list (soft-deleted)
    list_resp = await client.get(f"/comments?issue_id={issue_id}")
    ids_in_list = [c["id"] for c in list_resp.json()]
    assert comment_id not in ids_in_list


@pytest.mark.asyncio
async def test_comment_on_nonexistent_issue(client):
    """POST /comments — commenting on a non-existent issue returns 404."""
    token1, _, _ = await _create_issue_and_users(client)
    fake_id = str(uuid.uuid4())

    response = await client.post(
        "/comments",
        json={
            "issue_id": fake_id,
            "content": "Comment on a non-existent issue for testing.",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_comment_rejected(client):
    """POST /comments — without a Bearer token the endpoint returns 401."""
    _, _, issue_id = await _create_issue_and_users(client)

    response = await client.post(
        "/comments",
        json={
            "issue_id": issue_id,
            "content": "Attempting to comment without authentication.",
        },
        # No Authorization header
    )

    assert response.status_code == 401

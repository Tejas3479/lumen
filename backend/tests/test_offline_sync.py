"""
Tests: Offline Sync and Idempotency

Covers:
  - Sync a new draft creates one issue
  - Syncing the same draft twice is idempotent (returns same issue_id)
  - Batch sync creates all issues in one request
  - Missing required fields returns a failure entry (not a 500)
  - Unauthenticated sync (anonymous draft) is accepted
"""
import pytest
import uuid
from datetime import datetime, timezone


# ─── Helpers ──────────────────────────────────────────────────

def _make_draft(key: str | None = None, overrides: dict | None = None) -> dict:
    """Build a valid draft payload dict."""
    base = {
        "device_idempotency_key": key or str(uuid.uuid4()),
        "created_locally_at": datetime.now(timezone.utc).isoformat(),
        "title": "Offline sync test pothole report on civic road",
        "description": "This report was queued offline and is now syncing to the server.",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "is_anonymous": False,
        "is_emergency": False,
        "severity": "medium",
    }
    if overrides:
        base.update(overrides)
    return base


# ─── Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_offline_sync_creates_issue(client):
    """POST /offline/sync with a new draft must create exactly one issue."""
    key = str(uuid.uuid4())
    resp = await client.post("/offline/sync", json={"drafts": [_make_draft(key)]})

    assert resp.status_code == 200, f"Sync failed: {resp.text}"
    data = resp.json()
    assert len(data["synced"]) == 1
    assert data["synced"][0]["key"] == key
    assert "issue_id" in data["synced"][0]
    assert len(data["failed"]) == 0
    assert len(data["skipped"]) == 0


@pytest.mark.asyncio
async def test_offline_sync_idempotent(client):
    """
    Syncing the same draft key twice must NOT create duplicate issues.
    First call → synced; second call → skipped.  Same issue_id returned.
    """
    key = str(uuid.uuid4())
    payload = {"drafts": [_make_draft(key)]}

    r1 = await client.post("/offline/sync", json=payload)
    r2 = await client.post("/offline/sync", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200

    r1_data = r1.json()
    r2_data = r2.json()

    # First sync: issue created
    assert len(r1_data["synced"]) == 1, f"Expected 1 synced, got: {r1_data}"
    first_issue_id = r1_data["synced"][0]["issue_id"]

    # Second sync: must be skipped with same issue_id
    assert len(r2_data["skipped"]) == 1, f"Expected 1 skipped, got: {r2_data}"
    skipped_issue_id = r2_data["skipped"][0]["issue_id"]

    # Crucially — same issue
    assert first_issue_id == skipped_issue_id, (
        f"Idempotency broken: {first_issue_id} != {skipped_issue_id}"
    )


@pytest.mark.asyncio
async def test_offline_sync_multiple_drafts(client):
    """
    A single sync request with multiple distinct drafts creates one issue per draft.
    """
    drafts = [
        _make_draft(
            overrides={
                "title": f"Multi-draft offline sync test report number {i}",
                "latitude": 12.9716 + i * 0.001,
            }
        )
        for i in range(3)
    ]
    resp = await client.post("/offline/sync", json={"drafts": drafts})

    assert resp.status_code == 200, f"Batch sync failed: {resp.text}"
    data = resp.json()
    assert len(data["synced"]) == 3, f"Expected 3 synced, got: {data}"
    assert len(data["failed"]) == 0
    assert len(data["skipped"]) == 0

    # All issue IDs must be distinct
    issue_ids = [s["issue_id"] for s in data["synced"]]
    assert len(set(issue_ids)) == 3, "Duplicate issue IDs in batch sync response"


@pytest.mark.asyncio
async def test_offline_sync_partial_failure_continues_batch(client):
    """
    A draft with an invalid payload (too-short title) must go to 'failed',
    while valid drafts in the same batch still succeed.
    """
    good_key = str(uuid.uuid4())
    bad_key = str(uuid.uuid4())

    drafts = [
        _make_draft(good_key),  # valid
        _make_draft(bad_key, overrides={"title": "Hi", "description": "Short"}),  # invalid
    ]

    resp = await client.post("/offline/sync", json={"drafts": drafts})
    assert resp.status_code == 200, f"Sync returned non-200: {resp.text}"

    data = resp.json()
    synced_keys = {s["key"] for s in data["synced"]}
    failed_keys = {f["key"] for f in data["failed"]}

    # Good draft must succeed
    assert good_key in synced_keys, f"Good draft not in synced: {data}"
    # Bad draft must fail gracefully
    assert bad_key in failed_keys, f"Bad draft not in failed: {data}"


@pytest.mark.asyncio
async def test_offline_sync_unauthenticated_succeeds(client):
    """
    Offline sync endpoint must work without authentication
    (anonymous / guest users reporting issues offline).
    """
    key = str(uuid.uuid4())
    resp = await client.post("/offline/sync", json={"drafts": [_make_draft(key)]})

    assert resp.status_code == 200, f"Anonymous sync failed: {resp.text}"
    data = resp.json()
    assert len(data["synced"]) == 1
    assert data["synced"][0]["key"] == key


@pytest.mark.asyncio
async def test_offline_sync_returns_empty_lists_for_empty_batch(client):
    """
    Sending an empty drafts array must return 200 with all empty lists.
    """
    resp = await client.post("/offline/sync", json={"drafts": []})

    assert resp.status_code == 200
    data = resp.json()
    assert data["synced"] == []
    assert data["skipped"] == []
    assert data["failed"] == []


@pytest.mark.asyncio
async def test_offline_sync_emergency_issue(client):
    """
    An emergency draft must create an emergency issue.
    """
    key = str(uuid.uuid4())
    resp = await client.post("/offline/sync", json={
        "drafts": [_make_draft(key, overrides={"is_emergency": True})]
    })

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["synced"]) == 1
    issue_id = data["synced"][0]["issue_id"]

    # Verify the issue is actually marked emergency
    issue_resp = await client.get(f"/issues/{issue_id}")
    assert issue_resp.status_code == 200
    assert issue_resp.json()["is_emergency"] is True

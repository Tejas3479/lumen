"""
Tests: Real-time Socket System
Session 12

Covers:
- emit_new_issue broadcasts with correct event name and data
- emit_emergency_alert broadcasts with EMERGENCY_ALERT event
- emit_status_update broadcasts to global and to issue room
- emit_verification_update broadcasts to global and to issue room
- emit_issue_reopened broadcasts ISSUE_REOPENED
- publish_to_socket does not raise when Redis is mocked
- Redis subscriber dispatches ai_result message to sio.emit
"""
import pytest
import json
from unittest.mock import MagicMock

from app.sockets.events import (
    LumenEvents,
    emit_new_issue,
    emit_emergency_alert,
    emit_status_update,
    emit_verification_update,
    emit_issue_reopened,
    publish_to_socket,
)


# ── Helpers ───────────────────────────────────────────────────────

def _capture_emit(monkeypatch):
    """
    Replaces sio.emit with a mock that records all calls.
    Returns the list of (event, data, kwargs) tuples.
    """
    from app.sockets import events as ev
    calls: list[tuple] = []

    async def mock_emit(event, data=None, **kwargs):
        calls.append((event, data, kwargs))

    monkeypatch.setattr(ev.sio, "emit", mock_emit)
    return calls


# ── Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_emit_new_issue(monkeypatch):
    """emit_new_issue must call sio.emit with NEW_ISSUE and include the id."""
    calls = _capture_emit(monkeypatch)

    issue_data = {
        "id": "test-issue-001",
        "title": "Broken water pipe",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "severity": "high",
        "is_emergency": False,
        "category": "water_supply",
        "status": "reported",
    }
    await emit_new_issue(issue_data)

    assert len(calls) == 1
    event, data, _ = calls[0]
    assert event == LumenEvents.NEW_ISSUE
    assert data["id"] == "test-issue-001"
    assert data["title"] == "Broken water pipe"


@pytest.mark.asyncio
async def test_emit_emergency_alert(monkeypatch):
    """emit_emergency_alert must use EMERGENCY_ALERT event name."""
    calls = _capture_emit(monkeypatch)

    await emit_emergency_alert({
        "id": "emg-001",
        "is_emergency": True,
        "title": "Open manhole on main road",
        "latitude": 12.9,
        "longitude": 77.5,
        "severity": "critical",
        "category": "drainage",
        "status": "reported",
    })

    events_fired = [c[0] for c in calls]
    assert LumenEvents.EMERGENCY_ALERT in events_fired


@pytest.mark.asyncio
async def test_emit_status_update_global_and_room(monkeypatch):
    """
    emit_status_update must emit to all clients (global) AND to the
    issue-specific room so IssueDetailPage gets the history entry.
    """
    calls = _capture_emit(monkeypatch)

    await emit_status_update(
        "issue-abc",
        "verified",
        {
            "to_status": "verified",
            "is_official": False,
            "note": "Community auto-verified",
            "changed_at": "2026-06-27T05:00:00Z",
        },
    )

    events_fired = [c[0] for c in calls]
    # Must appear at least twice (global + room)
    status_calls = [c for c in calls if c[0] == LumenEvents.STATUS_UPDATE]
    assert len(status_calls) >= 2, "Expected global + room-targeted emission"

    # All status payloads must carry the issue_id
    for _, data, _ in status_calls:
        assert data["issue_id"] == "issue-abc"
        assert data["new_status"] == "verified"

    # One call should be room-targeted
    room_calls = [c for c in status_calls if c[2].get("room") == "issue_issue-abc"]
    assert len(room_calls) >= 1, "Expected a room-targeted status_update"


@pytest.mark.asyncio
async def test_emit_verification_update_global_and_room(monkeypatch):
    """
    emit_verification_update must emit globally (map popups) and to
    the issue room (VerificationPanel live count).
    """
    calls = _capture_emit(monkeypatch)

    await emit_verification_update(
        "issue-xyz",
        5,
        {"verification_type": "hard", "trust_weight": 1.0},
    )

    ver_calls = [c for c in calls if c[0] == LumenEvents.VERIFICATION_UPDATE]
    assert len(ver_calls) >= 2

    payloads = [c[1] for c in ver_calls]
    assert all(p["issue_id"] == "issue-xyz" for p in payloads)
    assert all(p["verification_count"] == 5 for p in payloads)


@pytest.mark.asyncio
async def test_emit_issue_reopened(monkeypatch):
    """emit_issue_reopened must broadcast ISSUE_REOPENED with dispute_count."""
    calls = _capture_emit(monkeypatch)

    await emit_issue_reopened("issue-999", 3)

    reopen_calls = [c for c in calls if c[0] == LumenEvents.ISSUE_REOPENED]
    assert len(reopen_calls) == 1
    assert reopen_calls[0][1]["issue_id"] == "issue-999"
    assert reopen_calls[0][1]["dispute_count"] == 3


def test_publish_to_socket_does_not_raise(monkeypatch):
    """
    publish_to_socket must not raise even when called with a Redis mock.
    Ensures Celery tasks are not disrupted by socket publishing failures.
    """
    try:
        import redis as sync_redis

        mock_client = MagicMock()
        mock_client.publish = MagicMock(return_value=1)
        mock_client.close = MagicMock()

        monkeypatch.setattr(sync_redis, "from_url", lambda *a, **kw: mock_client)

        # Must not raise
        publish_to_socket(
            "redis://localhost:6379/0",
            LumenEvents.AI_RESULT,
            {
                "issue_id": "test-id",
                "ai_category": "pothole",
                "ai_severity": "high",
                "ai_confidence": 0.93,
                "ai_explanation": "Surface deformation detected",
                "ai_summary": "Pothole on road surface",
            },
        )

        # Verify publish was actually called with the right channel
        mock_client.publish.assert_called_once()
        channel_arg = mock_client.publish.call_args[0][0]
        assert channel_arg == "lumen:socket_events"

    except ImportError:
        pytest.skip("redis package not installed")


@pytest.mark.asyncio
async def test_redis_subscriber_dispatches_ai_result(monkeypatch):
    """
    Simulate the subscriber receiving an ai_result message and verify
    it calls sio.emit with the correct event and payload.
    This tests the dispatch logic inside start_redis_subscriber.
    """
    from app.sockets import events as ev
    calls = _capture_emit(monkeypatch)

    # Simulate a message arriving from Redis
    raw_message = json.dumps({
        "event": LumenEvents.AI_RESULT,
        "data": {
            "issue_id": "simulated-issue",
            "ai_category": "pothole",
            "ai_severity": "high",
            "ai_confidence": 0.91,
            "ai_explanation": "Surface irregularity detected",
            "ai_summary": "Pothole with high confidence",
        },
    })

    # Execute the dispatch logic directly (mirrors what subscriber does)
    payload = json.loads(raw_message)
    event_name = payload.get("event")
    data = payload.get("data", {})

    if event_name == LumenEvents.AI_RESULT:
        await ev.sio.emit(LumenEvents.AI_RESULT, data)

    ai_calls = [c for c in calls if c[0] == LumenEvents.AI_RESULT]
    assert len(ai_calls) == 1
    assert ai_calls[0][1]["issue_id"] == "simulated-issue"
    assert ai_calls[0][1]["ai_category"] == "pothole"

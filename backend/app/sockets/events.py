"""
Lumen WebSocket Events
All 13 real-time events emitted via Socket.IO.
Frontend stores consume these events via useSocket hook.

Session 12 additions:
- Redis pub/sub subscriber (start_redis_subscriber) for Celery→Socket.IO bridge
- publish_to_socket synchronous helper for Celery workers
- leave_issue_room event handler
- emit_to_issue_room helper for room-targeted emission
- Room-aware variants of emit_status_update, emit_verification_update,
  emit_comment_added so clients only receive updates for issues they view
"""
import asyncio
import json
import socketio
from app.logging_config import logger

# Create Socket.IO async server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",  # Tighten in production
    logger=False,
    engineio_logger=False,
)


# Event names — single source of truth
class LumenEvents:
    NEW_ISSUE = "new_issue"
    ISSUE_UPDATED = "issue_updated"
    STATUS_UPDATE = "status_update"
    AI_RESULT = "ai_result"
    VERIFICATION_UPDATE = "verification_update"
    COMMENT_ADDED = "comment_added"
    LEADERBOARD_UPDATE = "leaderboard_update"
    EMERGENCY_ALERT = "emergency_alert"
    ISSUE_REOPENED = "issue_reopened"
    RESOLUTION_FEEDBACK_RECEIVED = "resolution_feedback_received"
    OFFLINE_SYNC_COMPLETED = "offline_sync_completed"
    ADMIN_ACTION = "admin_action"
    HOTSPOT_UPDATE = "hotspot_update"


# ── Broadcast emitters ────────────────────────────────────────────

async def emit_new_issue(issue_data: dict) -> None:
    """Broadcast new issue to all connected clients."""
    await sio.emit(LumenEvents.NEW_ISSUE, issue_data)
    logger.info("Socket emitted", extra={"event": LumenEvents.NEW_ISSUE, "issue_id": issue_data.get("id")})


async def emit_issue_updated(issue_id: str, updates: dict) -> None:
    """Broadcast issue updates (e.g. AI correction or official edits) to all clients and issue room."""
    payload = {"issue_id": issue_id, "updates": updates}
    await sio.emit(LumenEvents.ISSUE_UPDATED, payload)
    await emit_to_issue_room(issue_id, LumenEvents.ISSUE_UPDATED, payload)
    logger.info("Socket emitted", extra={"event": LumenEvents.ISSUE_UPDATED, "issue_id": issue_id})


async def emit_status_update(issue_id: str, new_status: str, history_entry: dict) -> None:
    """
    Broadcast status change.
    Emits to ALL clients (map marker update) and also to the
    issue-specific room (status timeline update in IssueDetailPage).
    """
    payload = {
        "issue_id": issue_id,
        "new_status": new_status,
        "history_entry": history_entry,
    }
    # Global broadcast — map markers need to update their colour
    await sio.emit(LumenEvents.STATUS_UPDATE, payload)
    # Room-targeted — IssueDetailPage timeline gets the history entry
    await sio.emit(LumenEvents.STATUS_UPDATE, payload, room=f"issue_{issue_id}")
    logger.info("Socket emitted", extra={"event": LumenEvents.STATUS_UPDATE, "issue_id": issue_id})


async def emit_ai_result(issue_id: str, ai_data: dict) -> None:
    """Broadcast AI categorization result after async processing."""
    payload = {"issue_id": issue_id, **ai_data}
    await sio.emit(LumenEvents.AI_RESULT, payload)


async def emit_verification_update(issue_id: str, verification_count: int, verification_data: dict) -> None:
    """
    Broadcast verification count change.
    Emits globally (map popups) and to issue room (VerificationPanel).
    """
    payload = {
        "issue_id": issue_id,
        "verification_count": verification_count,
        "verification": verification_data,
    }
    await sio.emit(LumenEvents.VERIFICATION_UPDATE, payload)
    await sio.emit(LumenEvents.VERIFICATION_UPDATE, payload, room=f"issue_{issue_id}")


async def emit_comment_added(issue_id: str, comment_data: dict) -> None:
    """
    Broadcast new comment only to clients viewing this issue.
    Comments are not relevant to the global map view.
    """
    payload = {"issue_id": issue_id, "comment": comment_data}
    await sio.emit(LumenEvents.COMMENT_ADDED, payload, room=f"issue_{issue_id}")


async def emit_leaderboard_update(top_users: list) -> None:
    """Broadcast leaderboard change when top-20 ranking shifts."""
    await sio.emit(LumenEvents.LEADERBOARD_UPDATE, {"top_users": top_users})


async def emit_emergency_alert(issue_data: dict) -> None:
    """Broadcast emergency issue to all connected clients including admins."""
    await sio.emit(LumenEvents.EMERGENCY_ALERT, issue_data)
    logger.warning("Emergency alert emitted", extra={"issue_id": issue_data.get("id")})


async def emit_issue_reopened(issue_id: str, dispute_count: int) -> None:
    """Broadcast issue reopen after dispute threshold."""
    payload = {"issue_id": issue_id, "dispute_count": dispute_count}
    await sio.emit(LumenEvents.ISSUE_REOPENED, payload)


async def emit_resolution_feedback(issue_id: str, feedback_data: dict) -> None:
    """Broadcast resolution feedback received."""
    payload = {"issue_id": issue_id, "feedback": feedback_data}
    await sio.emit(LumenEvents.RESOLUTION_FEEDBACK_RECEIVED, payload)


async def emit_offline_sync_completed(user_session: str, synced: list, skipped: list) -> None:
    """Notify specific session that their offline drafts are synced."""
    payload = {"synced": synced, "skipped": skipped}
    await sio.emit(LumenEvents.OFFLINE_SYNC_COMPLETED, payload, room=user_session)


async def emit_admin_action(action: str, target_id: str, actor_id: str) -> None:
    """Broadcast admin action to admin clients."""
    payload = {"action": action, "target_id": target_id, "actor_id": actor_id}
    await sio.emit(LumenEvents.ADMIN_ACTION, payload)


async def emit_hotspot_update(hotspots: list) -> None:
    """Broadcast updated hotspot predictions."""
    await sio.emit(LumenEvents.HOTSPOT_UPDATE, {"hotspots": hotspots})


# ── Room helpers ──────────────────────────────────────────────────

async def emit_to_issue_room(issue_id: str, event: str, data: dict) -> None:
    """
    Emit any event to clients watching a specific issue.
    Convenience wrapper over sio.emit(event, data, room=f"issue_{issue_id}").
    """
    await sio.emit(event, data, room=f"issue_{issue_id}")


# ── Socket.IO connection lifecycle ────────────────────────────────

@sio.event
async def connect(sid, environ, auth):
    logger.info("Client connected", extra={"sid": sid})


@sio.event
async def disconnect(sid):
    logger.info("Client disconnected", extra={"sid": sid})


@sio.event
async def join_issue_room(sid, data):
    """Client joins a room for real-time updates on a specific issue."""
    issue_id = data.get("issue_id")
    if issue_id:
        await sio.enter_room(sid, f"issue_{issue_id}")
        logger.info("Client joined issue room", extra={"sid": sid, "issue_id": issue_id})


@sio.event
async def leave_issue_room(sid, data):
    """Client leaves issue room when navigating away from IssueDetailPage."""
    issue_id = data.get("issue_id")
    if issue_id:
        await sio.leave_room(sid, f"issue_{issue_id}")
        logger.info("Client left issue room", extra={"sid": sid, "issue_id": issue_id})


# ── Redis pub/sub subscriber ──────────────────────────────────────
# Session 12: Celery workers run in a separate process and cannot call
# sio.emit directly. Instead they publish JSON messages to Redis channel
# "lumen:socket_events", and this subscriber picks them up and forwards
# them as Socket.IO events to connected clients.
#
# Message format: {"event": "<LumenEvents.CONSTANT>", "data": {...}}


async def start_redis_subscriber(redis_url: str) -> None:
    """
    Async Redis pub/sub subscriber.
    Started as a background asyncio task on FastAPI startup.
    Reconnects automatically if Redis becomes unavailable.
    """
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning(
            "redis.asyncio not available — Celery→Socket.IO bridge disabled. "
            "Install redis[asyncio] to enable."
        )
        return

    while True:  # Outer reconnect loop
        try:
            client = aioredis.from_url(redis_url, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe("lumen:socket_events")
            logger.info("Redis subscriber listening on lumen:socket_events")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    event_name: str = payload.get("event", "")
                    data: dict = payload.get("data", {})

                    # Only Celery-published events flow through this channel.
                    # Direct route-handler emissions use sio.emit() themselves.
                    if event_name == LumenEvents.AI_RESULT:
                        await sio.emit(LumenEvents.AI_RESULT, data)
                    elif event_name == LumenEvents.LEADERBOARD_UPDATE:
                        await sio.emit(LumenEvents.LEADERBOARD_UPDATE, data)
                    elif event_name == LumenEvents.HOTSPOT_UPDATE:
                        await sio.emit(LumenEvents.HOTSPOT_UPDATE, data)
                    # All other events are emitted directly in route handlers

                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning(
                        "Redis subscriber parse error",
                        extra={"error": str(exc)},
                    )

        except Exception as exc:
            logger.warning(
                "Redis subscriber disconnected — reconnecting in 5s",
                extra={"error": str(exc)},
            )
            await asyncio.sleep(5)


def publish_to_socket(redis_url: str, event: str, data: dict) -> None:
    """
    Synchronous helper for Celery tasks to publish socket events to Redis.
    Called from Celery worker context (sync) — uses the sync redis client.

    Already used by ai_categorizer.py (Session 7). This function is the
    mirror of the async subscriber above: Celery publishes, FastAPI consumes.

    Does not raise — socket publishing failures must not abort Celery tasks.
    """
    try:
        import redis as sync_redis  # type: ignore[import]
        client = sync_redis.from_url(redis_url, decode_responses=True)
        client.publish(
            "lumen:socket_events",
            json.dumps({"event": event, "data": data}),
        )
        client.close()
    except Exception as exc:
        logger.warning(
            "publish_to_socket failed",
            extra={"event": event, "error": str(exc)},
        )

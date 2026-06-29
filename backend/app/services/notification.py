"""
Lumen Notification Service
Handles browser push notifications and in-app notification dispatch.

Architecture:
  - Uses Web Push API (RFC 8030) via pywebpush library
  - VAPID keys authenticate the push server
  - Subscriptions stored in user.notification_preferences JSONB
  - Async dispatch via Celery task to avoid blocking HTTP response

Notification triggers (all configurable per-user):
  - status_change: issue status changes
  - verification: someone verifies your issue
  - official_comment: official posts a comment on your issue
  - resolution: your issue is marked resolved (triggers confirmation prompt)
  - nearby_emergency: emergency issue reported within user's radius
"""
import json
from typing import Optional
from app.config import settings
from app.logging_config import logger


def _get_fcm_app():
    """Returns Firebase Admin App singleton."""
    import firebase_admin
    from firebase_admin import credentials

    if not settings.firebase_credentials_path or not settings.fcm_enabled:
        return None

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.firebase_credentials_path)
            firebase_admin.initialize_app(cred)
        return firebase_admin.get_app()
    except Exception as e:
        logger.warning("Firebase Admin init failed", extra={"error": str(e)})
        return None


async def send_fcm_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    """
    Sends a push notification via Firebase Cloud Messaging.
    FCM works on Android, iOS (16.4+), and desktop Chrome.
    Returns True on success, False on failure.
    """
    app = _get_fcm_app()
    if not app:
        return False

    try:
        from firebase_admin import messaging
        import asyncio

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=fcm_token,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1)
                )
            ),
        )

        def _send():
            return messaging.send(message, app=app)

        await asyncio.get_event_loop().run_in_executor(None, _send)
        return True
    except Exception as e:
        logger.warning("FCM send failed", extra={"error": str(e)})
        return False


async def send_push_notification(
    subscription: dict,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "lumen",
) -> bool:
    """
    Sends push notification. Tries FCM first, then Web Push VAPID.
    subscription dict may contain: fcm_token, endpoint, keys.
    """
    # Try FCM if token available
    fcm_token = subscription.get("fcm_token")
    if fcm_token:
        success = await send_fcm_notification(
            fcm_token=fcm_token,
            title=title,
            body=body,
            data={"url": url, "tag": tag},
        )
        if success:
            return True

    # Fall back to Web Push VAPID
    if not settings.push_vapid_private_key or not settings.push_vapid_public_key:
        logger.info("VAPID keys not configured — skipping push notification")
        return False

    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info=subscription,
            data=json.dumps({
                "title": title,
                "body": body,
                "url": url,
                "tag": tag,
            }),
            vapid_private_key=settings.push_vapid_private_key,
            vapid_claims={
                "sub": f"mailto:{settings.push_vapid_email}",
            },
        )
        return True
    except ImportError:
        logger.warning("pywebpush not installed — push notifications disabled")
        return False
    except Exception as e:
        logger.warning("Push notification failed", extra={"error": str(e)})
        return False


async def notify_issue_status_change(
    reporter_id: Optional[str],
    issue_id: str,
    issue_title: str,
    new_status: str,
    db,
) -> None:
    """
    Notifies the issue reporter when status changes.
    Respects notification_preferences.notify_on_status_change.
    """
    if not reporter_id:
        return  # Anonymous reporters cannot receive push notifications

    try:
        from sqlalchemy import select
        from app.models import User

        result = await db.execute(select(User).where(User.id == reporter_id))
        user = result.scalar_one_or_none()
        if not user:
            return

        prefs = user.notification_preferences or {}
        if not prefs.get("notify_on_status_change", True):
            return

        status_labels = {
            "verified": "Community verified your report",
            "assigned": "Your report was assigned to a team",
            "in_progress": "Work has started on your report",
            "resolved": "Officials say your report is resolved",
            "disputed": "Your report resolution is disputed",
            "escalated": "Your report has been escalated due to SLA delay",
        }
        label = status_labels.get(new_status)
        if not label:
            return

        subscription = prefs.get("push_subscription")
        if subscription:
            await send_push_notification(
                subscription=subscription,
                title=label,
                body=issue_title[:100],
                url=f"/issues/{issue_id}",
                tag=f"status-{issue_id}",
            )
            logger.info(
                "Status change notification sent",
                extra={
                    "user_id": str(reporter_id),
                    "issue_id": issue_id,
                    "new_status": new_status,
                }
            )
    except Exception as e:
        logger.warning("notify_issue_status_change failed", extra={"error": str(e)})


async def notify_resolution_prompt(
    reporter_id: Optional[str],
    issue_id: str,
    issue_title: str,
    db,
) -> None:
    """
    Sends "Is it really fixed?" notification when issue is marked resolved.
    Critical for the resolution confirmation flow (Sessions 4 + 11).
    """
    if not reporter_id:
        return

    try:
        from sqlalchemy import select
        from app.models import User

        result = await db.execute(select(User).where(User.id == reporter_id))
        user = result.scalar_one_or_none()
        if not user:
            return

        prefs = user.notification_preferences or {}
        if not prefs.get("notify_on_resolution", True):
            return

        subscription = prefs.get("push_subscription")
        if subscription:
            await send_push_notification(
                subscription=subscription,
                title="Is it really fixed? 🏁",
                body=f"{issue_title[:80]} — Tap to confirm or dispute",
                url=f"/issues/{issue_id}",
                tag=f"resolve-{issue_id}",
            )
    except Exception as e:
        logger.warning("notify_resolution_prompt failed", extra={"error": str(e)})


async def notify_verification(
    reporter_id: Optional[str],
    issue_id: str,
    issue_title: str,
    verifier_display_name: str,
    db,
) -> None:
    """
    Notifies the reporter when someone verifies their issue.
    Respects notification_preferences.notify_on_verification.
    """
    if not reporter_id:
        return

    try:
        from sqlalchemy import select
        from app.models import User

        result = await db.execute(select(User).where(User.id == reporter_id))
        user = result.scalar_one_or_none()
        if not user:
            return

        prefs = user.notification_preferences or {}
        if not prefs.get("notify_on_verification", True):
            return

        subscription = prefs.get("push_subscription")
        if subscription:
            await send_push_notification(
                subscription=subscription,
                title=f"{verifier_display_name} verified your report",
                body=issue_title[:100],
                url=f"/issues/{issue_id}",
                tag=f"verify-{issue_id}",
            )
    except Exception as e:
        logger.warning("notify_verification failed", extra={"error": str(e)})


async def notify_official_comment(
    reporter_id: Optional[str],
    issue_id: str,
    issue_title: str,
    commenter_name: str,
    comment_preview: str,
    db,
) -> None:
    """
    Notifies the reporter when an official posts a comment on their issue.
    Respects notification_preferences.notify_on_official_comment.
    """
    if not reporter_id:
        return

    try:
        from sqlalchemy import select
        from app.models import User

        result = await db.execute(select(User).where(User.id == reporter_id))
        user = result.scalar_one_or_none()
        if not user:
            return

        prefs = user.notification_preferences or {}
        if not prefs.get("notify_on_official_comment", True):
            return

        subscription = prefs.get("push_subscription")
        if subscription:
            await send_push_notification(
                subscription=subscription,
                title=f"Official update from {commenter_name}",
                body=comment_preview[:100],
                url=f"/issues/{issue_id}",
                tag=f"comment-{issue_id}",
            )
    except Exception as e:
        logger.warning("notify_official_comment failed", extra={"error": str(e)})

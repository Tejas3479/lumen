"""
Lumen Maintenance Tasks
Celery Beat tasks for periodic housekeeping.

Tasks:
  - cleanup_guest_users: Purges guest user records older than 30 days.
    Runs daily at 3 AM IST. Guest users have no email, no community history,
    and no persistent data — safe to purge on a rolling basis.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app
from app.logging_config import logger


@celery_app.task(
    name="app.services.maintenance.cleanup_guest_users",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def cleanup_guest_users(self):
    """
    Deletes guest user records older than 30 days.
    Runs daily at 3 AM IST via Celery Beat.

    Guest users:
      - Have is_guest=True
      - Have no email, no password, no leaderboard entry
      - May have ephemeral votes/issues but those are already anonymous
      - After 30 days their session JWT has long expired
    """
    async def _cleanup():
        from app.celery_db import get_celery_session
        from app.models import User
        from sqlalchemy import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        async with get_celery_session() as db:
            try:
                result = await db.execute(
                    delete(User).where(
                        User.is_guest == True,  # noqa: E712
                        User.created_at < cutoff,
                    )
                )
                count = result.rowcount
                await db.commit()
                logger.info("Guest user cleanup complete", deleted=count)
                return count
            except Exception as e:
                await db.rollback()
                logger.error(
                    "Guest user cleanup failed — FK constraint violation likely. "
                    "Verify ondelete=SET NULL is applied to all user FK columns.",
                    error=str(e),
                )
                raise e

    try:
        deleted = asyncio.run(_cleanup())
        return {"status": "ok", "deleted": deleted}
    except Exception as exc:
        logger.error(
            "Guest user cleanup failed",
            extra={"error": str(exc), "retry": self.request.retries},
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Guest user cleanup max retries exceeded")
            return {"status": "failed"}

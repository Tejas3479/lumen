"""
Lumen Moderation Service

Handles community-driven content moderation:
  - Flag threshold auto-hide: 5+ distinct pending flags → issue hidden from public feed
  - Moderation queue for admin review: paginated list sorted by flag count desc
  - Flag lifecycle management: dismiss (false positive) or resolve (actioned)

Auto-hide rationale:
  The threshold of 5 flags before auto-hide is a balance between:
    - False positives from aggressive flagging (too low)
    - Harmful content staying visible too long (too high)
  Admin can always restore a hidden issue by changing status back to 'reported'.

Called by:
  - POST /issues/{id}/flag (issues.py) → process_flag after Flag DB write
  - GET  /admin/moderation (admin.py, Session 14) → get_moderation_queue
  - PATCH /admin/flags/{id} (admin.py, Session 14) → dismiss_flag / resolve_flag
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.models import Issue, Flag, IssueAuditLog
from app.logging_config import logger

# ── Thresholds ────────────────────────────────────────────────
AUTO_HIDE_FLAG_COUNT: int = 5      # Auto-hide after this many distinct pending flags
SPAM_STRIKE_WARNING: int = 3       # (Future) Warn user after this many spam flags on their reports
SPAM_STRIKE_BAN: int = 10          # (Future) Auto-ban consideration threshold


async def process_flag(
    issue_id: uuid.UUID,
    flagged_by_id: uuid.UUID,
    reason: str,
    db: AsyncSession,
) -> dict:
    """
    Processes a new flag on an issue after the Flag record has been created.

    Counts distinct pending flags for the issue. If the AUTO_HIDE_FLAG_COUNT
    threshold is reached, automatically sets issue status to 'closed' and
    creates an IssueAuditLog entry. An admin must review to restore visibility.

    Args:
        issue_id:      UUID of the flagged issue.
        flagged_by_id: UUID of the user who submitted the flag.
        reason:        Flag reason string (spam, inappropriate, duplicate, etc.).
        db:            Async SQLAlchemy session (caller must commit/flush).

    Returns:
        {
            'action': 'flagged' | 'auto_hidden',
            'flag_count': int   — total pending flags on the issue
        }
    """
    # Count all pending flags on this issue (including the one just added)
    flag_count_result = await db.execute(
        select(func.count(Flag.id)).where(
            Flag.issue_id == issue_id,
            Flag.status == "pending",
        )
    )
    flag_count = flag_count_result.scalar_one()

    action = "flagged"

    if flag_count >= AUTO_HIDE_FLAG_COUNT:
        # Fetch the issue — may not exist if issue_id is invalid
        issue_result = await db.execute(
            select(Issue).where(Issue.id == issue_id)
        )
        issue = issue_result.scalar_one_or_none()

        if issue and issue.status not in ("closed", "resolved"):
            old_status = issue.status
            issue.status = "closed"

            db.add(IssueAuditLog(
                issue_id=issue_id,
                actor_id=None,  # System action — no human actor
                action="auto_hidden",
                before_state={"status": old_status},
                after_state={
                    "status": "closed",
                    "reason": f"Auto-hidden: {flag_count} community flags",
                },
            ))

            action = "auto_hidden"
            logger.warning(
                "Issue auto-hidden by flag threshold",
                extra={
                    "issue_id": str(issue_id),
                    "flag_count": flag_count,
                    "threshold": AUTO_HIDE_FLAG_COUNT,
                }
            )

    await db.flush()
    return {"action": action, "flag_count": flag_count}


async def get_moderation_queue(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """
    Returns a paginated list of issues with pending flags, sorted by flag count
    descending (highest-risk content first).

    Used by the admin moderation dashboard (Session 14).

    Args:
        db:       Async SQLAlchemy session.
        page:     1-based page number.
        per_page: Items per page (default 20, max enforced by route).

    Returns:
        {
            'items': [{issue_id, title, status, flag_count, ward, created_at}],
            'page': int,
            'per_page': int,
        }
    """
    # Subquery: group pending flags by issue, count, order by count desc
    subquery = (
        select(
            Flag.issue_id,
            func.count(Flag.id).label("flag_count"),
        )
        .where(Flag.status == "pending")
        .group_by(Flag.issue_id)
        .order_by(desc("flag_count"))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .subquery()
    )

    result = await db.execute(
        select(Issue, subquery.c.flag_count)
        .join(subquery, Issue.id == subquery.c.issue_id)
        .order_by(desc(subquery.c.flag_count))
    )
    rows = result.all()

    return {
        "items": [
            {
                "issue_id": str(row.Issue.id),
                "title": row.Issue.title,
                "status": row.Issue.status,
                "flag_count": row.flag_count,
                "ward": row.Issue.ward,
                "latitude": row.Issue.latitude,
                "longitude": row.Issue.longitude,
                "created_at": row.Issue.created_at.isoformat(),
            }
            for row in rows
        ],
        "page": page,
        "per_page": per_page,
    }


async def dismiss_flag(
    flag_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    """
    Marks a flag as 'dismissed' (false positive — no action needed).

    Called by PATCH /admin/flags/{flag_id}/dismiss (Session 14).

    Args:
        flag_id:     UUID of the Flag record to dismiss.
        reviewer_id: UUID of the admin who reviewed.
        db:          Async SQLAlchemy session.

    Returns:
        True if the flag was found and dismissed, False if not found.
    """
    result = await db.execute(select(Flag).where(Flag.id == flag_id))
    flag = result.scalar_one_or_none()

    if flag is None:
        return False

    flag.status = "dismissed"
    flag.reviewed_by = reviewer_id
    flag.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "Flag dismissed",
        extra={
            "flag_id": str(flag_id),
            "reviewer_id": str(reviewer_id),
            "issue_id": str(flag.issue_id),
        }
    )
    return True


async def resolve_flag(
    flag_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    """
    Marks a flag as 'reviewed' (actioned — content was moderated).

    Called by PATCH /admin/flags/{flag_id}/resolve (Session 14).

    Args:
        flag_id:     UUID of the Flag record to resolve.
        reviewer_id: UUID of the admin who took action.
        db:          Async SQLAlchemy session.

    Returns:
        True if the flag was found and resolved, False if not found.
    """
    result = await db.execute(select(Flag).where(Flag.id == flag_id))
    flag = result.scalar_one_or_none()

    if flag is None:
        return False

    flag.status = "reviewed"
    flag.reviewed_by = reviewer_id
    flag.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "Flag resolved (actioned)",
        extra={
            "flag_id": str(flag_id),
            "reviewer_id": str(reviewer_id),
            "issue_id": str(flag.issue_id),
        }
    )
    return True

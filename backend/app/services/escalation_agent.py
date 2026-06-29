"""
Lumen Proactive Escalation Agent
Celery Beat task that runs every 30 minutes.
Identifies stalled issues exceeding their SLA and escalates them.

SLA thresholds (from Category.avg_resolution_days, with multiplier):
  - Reported, not verified in 48 hours → escalate
  - Assigned, not in_progress in 24 hours → escalate
  - In_progress, not resolved after 2× avg_resolution_days → escalate
  - Critical severity: all thresholds halved

Agent behavior:
  1. Query all stalled issues
  2. For each stalled issue, reason about escalation level
  3. Send escalation notification to assigned official
  4. Update issue.escalation_count and escalated_at
  5. If escalation_count >= 3: flag for admin review
  6. Log all actions for audit trail
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

from app.celery_app import celery_app
from app.logging_config import logger


def _get_sla_hours(category_name: str, severity: str, stage: str) -> float:
    """
    Returns the SLA in hours for a given category + severity + lifecycle stage.
    """
    base_hours = {
        "pothole": 120,       # 5 days
        "water_leakage": 72,  # 3 days
        "streetlight": 96,    # 4 days
        "garbage": 48,        # 2 days
        "drainage": 168,      # 7 days
        "other": 240,         # 10 days
    }.get(category_name or "other", 168)

    severity_factor = {
        "critical": 0.25,
        "high": 0.5,
        "medium": 1.0,
        "low": 2.0,
    }.get(severity, 1.0)

    stage_factor = {
        "unverified": 0.4,   # Should be verified in 40% of total SLA
        "assigned": 0.2,     # Should start in 20% of total SLA
        "in_progress": 2.0,  # Allow 2× SLA for active work
    }.get(stage, 1.0)

    return base_hours * severity_factor * stage_factor


async def _find_stalled_issues(db) -> list:
    """
    Queries for issues that have exceeded their stage SLA.
    Returns list of (issue, stall_type, hours_overdue).
    """
    from app.models import Issue, Category, StatusHistory
    from sqlalchemy import select, and_, func
    from sqlalchemy.orm import selectinload

    now = datetime.now(timezone.utc)
    stalled = []

    # Stage 1: Reported but not verified
    unverified_cutoff = now - timedelta(hours=48)
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.category))
        .where(
            and_(
                Issue.status == "reported",
                Issue.created_at < unverified_cutoff,
                Issue.escalation_count < 3,
            )
        )
        .limit(20)
    )
    for issue in result.scalars().all():
        cat_name = issue.category.name if issue.category else "other"
        sla = _get_sla_hours(cat_name, issue.severity, "unverified")
        hours_since = (now - issue.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if hours_since > sla:
            stalled.append((issue, "unverified", round(hours_since - sla, 1)))

    # Stage 2: Assigned but not in_progress
    assigned_cutoff = now - timedelta(hours=24)
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.category))
        .where(
            and_(
                Issue.status == "assigned",
                Issue.updated_at < assigned_cutoff,
                Issue.escalation_count < 3,
            )
        )
        .limit(20)
    )
    for issue in result.scalars().all():
        cat_name = issue.category.name if issue.category else "other"
        sla = _get_sla_hours(cat_name, issue.severity, "assigned")
        hours_since = (now - issue.updated_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if hours_since > sla:
            stalled.append((issue, "assigned_stalled", round(hours_since - sla, 1)))

    # Stage 3: In progress but overdue
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.category))
        .where(
            and_(
                Issue.status == "in_progress",
                Issue.escalation_count < 3,
            )
        )
        .limit(20)
    )
    for issue in result.scalars().all():
        cat_name = issue.category.name if issue.category else "other"
        sla = _get_sla_hours(cat_name, issue.severity, "in_progress")
        hours_since = (now - issue.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if hours_since > sla:
            stalled.append((issue, "overdue", round(hours_since - sla, 1)))

    return stalled


async def _run_escalation_check():
    """
    Main escalation agent logic.
    Finds stalled issues and dispatches escalation notifications.
    """
    from app.celery_db import get_celery_session
    from app.models import Issue, StatusHistory, IssueAuditLog
    from app.services.notification import notify_issue_status_change
    from datetime import timezone
    import uuid

    async with get_celery_session() as db:
        stalled_issues = await _find_stalled_issues(db)

        if not stalled_issues:
            logger.info("Escalation agent: no stalled issues found")
            return {"escalated": 0}

        escalated_count = 0

        for issue, stall_type, hours_overdue in stalled_issues:
            try:
                # Update escalation tracking
                issue.escalation_count += 1
                issue.escalated_at = datetime.now(timezone.utc)

                # Add escalation note to status history
                escalation_note = (
                    f"⚠️ ESCALATION #{issue.escalation_count}: Issue has been "
                    f"{stall_type.replace('_', ' ')} for {hours_overdue:.1f} hours beyond SLA. "
                    f"Automatic escalation by Lumen Escalation Agent."
                )
                db.add(StatusHistory(
                    issue_id=issue.id,
                    from_status=issue.status,
                    to_status=issue.status,  # Status unchanged — only adding note
                    changed_by=None,  # System action
                    note=escalation_note,
                    is_official=True,
                    is_public=True,
                ))

                # Audit log
                db.add(IssueAuditLog(
                    issue_id=issue.id,
                    actor_id=None,
                    action="auto_escalated",
                    before_state={"escalation_count": issue.escalation_count - 1},
                    after_state={
                        "escalation_count": issue.escalation_count,
                        "stall_type": stall_type,
                        "hours_overdue": hours_overdue,
                    },
                ))

                # Notify assigned official
                if issue.reporter_id:
                    await notify_issue_status_change(
                        reporter_id=str(issue.reporter_id),
                        issue_id=str(issue.id),
                        issue_title=issue.title,
                        new_status="escalated",  # Virtual status for notification
                        db=db,
                    )

                escalated_count += 1

                logger.warning(
                    "Issue escalated",
                    extra={
                        "issue_id": str(issue.id),
                        "stall_type": stall_type,
                        "hours_overdue": hours_overdue,
                        "escalation_count": issue.escalation_count,
                    }
                )

            except Exception as e:
                logger.error(
                    "Escalation failed for issue",
                    extra={
                        "issue_id": str(issue.id),
                        "error": str(e),
                    }
                )

        await db.commit()
        return {"escalated": escalated_count, "checked": len(stalled_issues)}


@celery_app.task(name="app.services.escalation_agent.run_escalation_check")
def run_escalation_check():
    """
    Celery task: Proactive Escalation Agent.
    Runs every 30 minutes via Celery Beat.
    Finds stalled issues and escalates them autonomously.
    """
    try:
        result = asyncio.run(_run_escalation_check())
        logger.info(
            "Escalation agent complete",
            extra={
                "escalated": result.get("escalated", 0),
                "checked": result.get("checked", 0),
            }
        )
        return result
    except Exception as exc:
        logger.error("Escalation agent failed", extra={"error": str(exc)})
        return {"error": str(exc)}

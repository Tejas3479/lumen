"""
Lumen AI Routes
Provides three endpoints for the AI categorization pipeline:

  GET  /ai/status/{issue_id}     — poll AI result (Redis cache → DB fallback)
  POST /ai/feedback              — log user correction of AI suggestion (RLHF-lite)
  GET  /ai/categorize/{issue_id} — re-run AI categorization on existing issue
"""
import uuid
import json
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.dependencies import get_current_user_optional, DB, OptionalUser
from app.models import Issue, IssueAuditLog, TriageReport
from app.schemas import AIResultOut, AIFeedbackRequest, TriageReportOut
from app.config import settings
from app.exceptions import NotFoundError
from app.logging_config import logger

router = APIRouter()


@router.get("/status/{issue_id}")
async def get_ai_status(
    issue_id: uuid.UUID,
    db: DB = None,
):
    """
    Polling endpoint: Returns AI result for a given issue.

    Used by the frontend when WebSocket delivery of `ai_result` cannot be
    confirmed. The frontend should poll this endpoint after issue creation
    if the `ai_result` socket event is not received within ~10 seconds.

    Resolution order:
    1. Redis cache (fresh result, 5-minute TTL) — fastest
    2. Database fields (persisted result) — authoritative
    3. Pending status response — AI task still running

    Returns:
        - Result dict with source="cache" or source="database"
        - Pending dict with status="pending" if AI not yet completed
    """
    # ── Check Redis cache first ───────────────────────────
    try:
        import redis as redis_sync

        r = redis_sync.from_url(settings.redis_url, decode_responses=True)
        cached = r.get(f"lumen:ai_result:{issue_id}")
        r.close()

        if cached:
            data = json.loads(cached)
            data["source"] = "cache"
            logger.info("AI status served from Redis cache", extra={"issue_id": str(issue_id)})
            return data
    except Exception as e:
        # Redis unavailable — fall through to DB lookup
        logger.warning("Redis unavailable for AI status", extra={"error": str(e)})

    # ── Fall back to DB fields ────────────────────────────
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue", str(issue_id))

    if issue.ai_category:
        return {
            "issue_id": str(issue_id),
            "ai_category": issue.ai_category,
            "ai_severity": issue.ai_severity,
            "ai_confidence": issue.ai_confidence,
            "ai_explanation": issue.ai_explanation,
            "ai_summary": issue.ai_summary,
            "ai_reasoning": issue.ai_reasoning,
            "ai_alternatives": issue.ai_alternatives,
            "source": "database",
        }

    # ── AI task still running ─────────────────────────────
    return {
        "issue_id": str(issue_id),
        "status": "pending",
        "pending_since": issue.created_at.isoformat(),
        "message": "AI categorization is still processing. Check back in a few seconds.",
    }


@router.post("/feedback")
async def ai_feedback(
    payload: AIFeedbackRequest,
    db: DB = None,
    current_user: OptionalUser = None,
):
    """
    Logs a user correction of the AI suggestion (RLHF-lite feedback).

    When a user indicates the AI's category or severity was wrong, this
    endpoint records the correction and updates the issue with the
    user-verified values. The correction becomes the authoritative value —
    this endpoint does NOT re-run the AI.

    Writes an `ai_correction` entry to `IssueAuditLog` for future
    model improvement analysis.

    Returns:
        Confirmation dict with status="correction_logged"
    """
    result = await db.execute(select(Issue).where(Issue.id == payload.issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue", str(payload.issue_id))

    # Capture before-state for audit log
    before = {
        "ai_category": issue.ai_category,
        "ai_severity": issue.ai_severity,
        "category_id": str(issue.category_id) if issue.category_id else None,
        "severity": issue.severity,
    }

    # ── Apply correction ──────────────────────────────────
    issue.user_correction = True

    # Resolve corrected category name → category_id in DB
    if payload.corrected_category:
        from app.models import Category
        cat_result = await db.execute(
            select(Category).where(Category.name == payload.corrected_category)
        )
        category = cat_result.scalar_one_or_none()
        if category:
            issue.category_id = category.id
            logger.info(
                "Category corrected by user",
                extra={
                    "issue_id": str(payload.issue_id),
                    "from_ai": before["ai_category"],
                    "to_user": payload.corrected_category,
                    "resolved_id": str(category.id),
                }
            )
        else:
            logger.warning(
                "Corrected category name not found in DB",
                extra={"category_name": payload.corrected_category},
            )

    # Apply severity correction to the canonical severity field
    if payload.corrected_severity:
        issue.severity = payload.corrected_severity

    # ── Write audit log ───────────────────────────────────
    db.add(IssueAuditLog(
        issue_id=issue.id,
        actor_id=current_user.id if current_user else None,
        action="ai_correction",
        before_state=before,
        after_state={
            "corrected_category": payload.corrected_category,
            "corrected_severity": payload.corrected_severity,
            "user_comment": payload.user_comment,
        },
    ))

    await db.flush()

    # Emit real-time issue_updated socket event
    from app.sockets.events import emit_issue_updated
    updates = {"user_correction": True}
    if payload.corrected_category and "category" in locals() and category:
        updates["category_id"] = str(category.id)
        updates["category"] = {
            "id": str(category.id),
            "name": category.name,
            "display_name": category.display_name,
            "icon": category.icon,
            "color": category.color,
        }
        updates["ai_category"] = payload.corrected_category
    if payload.corrected_severity:
        updates["severity"] = payload.corrected_severity
        updates["ai_severity"] = payload.corrected_severity
    await emit_issue_updated(str(payload.issue_id), updates)

    logger.info(
        "AI correction logged",
        extra={
            "issue_id": str(payload.issue_id),
            "original_category": before["ai_category"],
            "corrected_category": payload.corrected_category,
            "corrected_severity": payload.corrected_severity,
            "actor": str(current_user.id) if current_user else "anonymous",
        }
    )

    return {
        "status": "correction_logged",
        "issue_id": str(payload.issue_id),
        "message": "Thank you for the correction. This helps improve future AI suggestions.",
    }


@router.get("/categorize/{issue_id}")
async def recategorize_issue(
    issue_id: uuid.UUID,
    db: DB = None,
):
    """
    Re-runs AI categorization on an existing issue.

    Useful when:
    - An issue was submitted without an image and media was added later
    - The initial AI result was a low-confidence fallback (confidence=0.0)
    - The user explicitly requests a fresh AI analysis

    Dispatches a new Celery task. Result will arrive via:
    - WebSocket `ai_result` event (if socket delivery works)
    - GET /ai/status/{issue_id} polling (fallback)

    Returns:
        Confirmation dict with status="queued"
    """
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue", str(issue_id))

    # Find the first photo media record for this issue
    from app.models import IssueMedia
    media_result = await db.execute(
        select(IssueMedia).where(
            IssueMedia.issue_id == issue_id,
            IssueMedia.media_type == "photo",
        ).limit(1)
    )
    media = media_result.scalar_one_or_none()
    image_path = media.file_path if media else None

    # Dispatch a fresh Celery task
    from app.services.ai_categorizer import categorize_issue_task
    categorize_issue_task.delay(
        str(issue_id),
        image_path,
        issue.description,
    )

    logger.info(
        "AI re-categorization task dispatched",
        extra={
            "issue_id": str(issue_id),
            "has_image": image_path is not None,
        }
    )

    return {
        "status": "queued",
        "issue_id": str(issue_id),
        "message": (
            "AI re-categorization started. "
            "Result will arrive via WebSocket or GET /ai/status/{id}."
        ),
    }


@router.get("/triage/{issue_id}", response_model=TriageReportOut)
async def get_triage_report(
    issue_id: uuid.UUID,
    db: DB,
):
    """
    Returns the triage agent's recommendation for an issue.
    Used by admin queue to show AI-recommended actions.
    If no triage report exists yet (agent still running), returns 202.
    """
    from app.models import TriageReport
    from app.schemas import TriageReportOut
    from fastapi import Response

    result = await db.execute(
        select(TriageReport).where(TriageReport.issue_id == issue_id)
    )
    triage = result.scalar_one_or_none()

    if not triage:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=202,
            content={"status": "pending", "message": "Triage agent is still reasoning…"}
        )

    return TriageReportOut.model_validate(triage)


@router.get("/agents/status")
async def get_agents_status(
    db: DB,
):
    """
    Returns status and run metrics for Lumen's AI and scheduled agents.
    """
    from sqlalchemy import func
    from app.models import TriageReport, Issue, WardReport

    # Triage Agent Metrics
    triage_count = await db.scalar(select(func.count(TriageReport.id)))

    # Escalation Agent Metrics
    escalated_count = await db.scalar(
        select(func.count(Issue.id)).where(
            Issue.escalation_count > 0,
            Issue.status.notin_(["resolved", "closed"])
        )
    )

    # Ward Report Agent Metrics
    ward_reports_count = await db.scalar(select(func.count(WardReport.id)))
    last_report_result = await db.execute(
        select(WardReport.generated_at).order_by(WardReport.generated_at.desc()).limit(1)
    )
    last_report_generated_at = last_report_result.scalar_one_or_none()

    return {
        "agents": [
            {
                "id": "triage_agent",
                "name": "Issue Triage Agent",
                "status": "active",
                "pattern": "ReAct (Reason + Act) with Gemini Function Calling",
                "model": "gemini-3.5-flash",
                "metrics": {
                    "total_triaged_issues": triage_count or 0
                }
            },
            {
                "id": "escalation_agent",
                "name": "Proactive Escalation Agent",
                "status": "active",
                "pattern": "Scheduled SLA Monitoring",
                "model": "rule-based",
                "frequency": "every 30 minutes",
                "metrics": {
                    "active_escalations": escalated_count or 0
                }
            },
            {
                "id": "ward_report_agent",
                "name": "Weekly Ward Report Agent",
                "status": "active",
                "pattern": "Scheduled Data Narration with Structured Output",
                "model": "gemini-3.5-flash",
                "frequency": "every Monday at 8 AM",
                "metrics": {
                    "total_reports_generated": ward_reports_count or 0,
                    "last_report_generated_at": last_report_generated_at.isoformat() if last_report_generated_at else None
                }
            }
        ]
    }


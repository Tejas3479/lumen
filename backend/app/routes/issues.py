"""
Lumen Issue Routes

POST   /issues                       — create issue (multipart)
GET    /issues                       — paginated feed with filters
GET    /issues/nearby                — geo-filtered map feed
POST   /issues/check-duplicates      — pre-submit duplicate check (JSON body)
GET    /issues/{id}                  — issue detail
PATCH  /issues/{id}                  — update issue (reporter/admin)
DELETE /issues/{id}                  — delete/close issue
PATCH  /issues/{id}/status           — change status (official/admin)
POST   /issues/{id}/assign           — assign to official
POST   /issues/{id}/flag             — flag for moderation
POST   /issues/{id}/support          — 'I see this too' vote
POST   /issues/{id}/resolution-feedback — confirm or dispute resolution
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select, update as sa_update, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_user_optional, get_current_user,
    get_official_or_admin,
    DB, OptionalUser, CurrentUser, OfficialUser,
)
from app.schemas import (
    IssueOut, IssueCreate, IssueUpdate, PaginatedIssues,
    StatusChangeRequest, AssignRequest, FlagCreate,
    VoteCreate, VoteOut, ResolutionFeedbackRequest, ResolutionFeedbackOut,
    VerifyRequest, VerificationOut,
)
from app.services.issue_service import (
    create_issue, get_issue_by_id, get_issues_paginated,
    get_issues_nearby, update_issue, change_issue_status, delete_issue,
)
from app.sockets.events import (
    emit_new_issue, emit_emergency_alert, emit_status_update,
    emit_issue_reopened, emit_resolution_feedback, emit_verification_update,
)
from app.models import (
    IssueMedia, Flag, Vote, Assignment, ResolutionFeedback,
    StatusHistory, IssueAuditLog,
)
from app.exceptions import ValidationError, ConflictError, SpamDetectedError
from app.config import settings
from app.logging_config import logger

router = APIRouter()


# ── POST /issues ──────────────────────────────────────────────

@router.post("", response_model=IssueOut, status_code=201)
async def create_issue_endpoint(
    title: str = Form(..., min_length=5, max_length=256),
    description: str = Form(..., min_length=10, max_length=5000),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: Optional[str] = Form(None),
    ward: Optional[str] = Form(None),
    severity: str = Form("medium"),
    is_anonymous: bool = Form(False),
    is_emergency: bool = Form(False),
    category_id: Optional[str] = Form(None),
    offline_draft_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: DB = None,
    current_user: OptionalUser = None,
):
    """
    Create a new civic issue report.
    Accepts multipart form (text + optional media files).

    Flow:
    1. Idempotency check for offline_draft_id
    2. Spam check
    3. Create issue + history + audit log
    4. Process and save media files
    5. Dispatch Celery AI task
    6. Emit new_issue (+ emergency_alert) socket events
    7. Return created issue immediately
    """
    # ── Idempotency: offline drafts ────────────────────────────
    if offline_draft_id:
        from app.models import OfflineDraft
        existing = await db.execute(
            sa_select(OfflineDraft).where(
                OfflineDraft.device_idempotency_key == offline_draft_id,
                OfflineDraft.synced == True,
            )
        )
        draft = existing.scalar_one_or_none()
        if draft and draft.synced_issue_id:
            return IssueOut.model_validate(
                await get_issue_by_id(draft.synced_issue_id, db)
            )

    # ── Spam check ────────────────────────────────────────────
    from app.services.spam_detector import check_spam
    is_spam, _, spam_reason = await check_spam(
        title=title,
        description=description,
        reporter=current_user,
        db=db,
    )
    if is_spam:
        raise SpamDetectedError(spam_reason)

    # ── Sanitize user text ────────────────────────────────────
    from app.utils.sanitize import sanitize_issue
    title, description = sanitize_issue(title, description)

    # ── Build payload ─────────────────────────────────────────
    payload = IssueCreate(
        title=title,
        description=description,
        latitude=latitude,
        longitude=longitude,
        address=address,
        ward=ward,
        severity=severity,
        is_anonymous=is_anonymous,
        is_emergency=is_emergency,
        category_id=uuid.UUID(category_id) if category_id else None,
        offline_draft_id=offline_draft_id,
    )

    # ── Create issue ──────────────────────────────────────────
    issue = await create_issue(payload=payload, db=db, reporter=current_user)

    # ── Process media ─────────────────────────────────────────
    if files:
        from app.utils.image_processing import process_upload
        for upload_file in files:
            if upload_file.filename:
                media_record = await process_upload(upload_file, issue.id, db)
                if media_record:
                    db.add(media_record)

    await db.flush()

    # ── Mark offline draft as synced ──────────────────────────
    if offline_draft_id:
        from app.models import OfflineDraft
        await db.execute(
            sa_update(OfflineDraft)
            .where(OfflineDraft.device_idempotency_key == offline_draft_id)
            .values(
                synced=True,
                synced_at=datetime.now(timezone.utc),
                synced_issue_id=issue.id,
            )
        )

    # ── Dispatch AI task ──────────────────────────────────────
    if settings.ai_enabled:
        try:
            from app.services.ai_categorizer import categorize_issue_task
            image_path = None
            if files:
                for f in files:
                    if f.content_type and f.content_type.startswith("image/"):
                        image_path = f"media/issues/{issue.id}/{f.filename}"
                        break
            categorize_issue_task.delay(str(issue.id), image_path, description)
        except Exception as e:
            logger.warning("AI task dispatch failed", extra={"error": str(e)})

        try:
            from app.services.triage_agent import run_triage_task
            run_triage_task.delay(str(issue.id))
            logger.info("Triage agent task dispatched", extra={"issue_id": str(issue.id)})
        except Exception as e:
            logger.warning("Triage agent dispatch failed", extra={"error": str(e)})

    # ── Reload with relations ─────────────────────────────────
    full_issue = await get_issue_by_id(issue.id, db)

    # ── Emit WebSocket events ─────────────────────────────────
    socket_data = {
        "id": str(issue.id),
        "latitude": issue.latitude,
        "longitude": issue.longitude,
        "title": issue.title,
        "description": issue.description,
        "severity": issue.severity,
        "is_emergency": issue.is_emergency,
        "category": full_issue.category.name if full_issue.category else "other",
        "status": "reported",
        "created_at": issue.created_at.isoformat(),
        "vote_count": 0,
        "verification_count": 0,
        "media": [],
    }
    await emit_new_issue(socket_data)
    if issue.is_emergency and settings.emergency_alerts_enabled:
        await emit_emergency_alert(socket_data)
        logger.warning("Emergency issue created", extra={"issue_id": str(issue.id)})

    # ── Gamification: award points for reporting ──────────────
    if current_user and not getattr(current_user, "is_guest", False):
        try:
            from app.services.gamification import award_points
            gam_event = await award_points(
                user_id=current_user.id,
                action="report_issue",
                db=db,
                issue_id=issue.id,
            )
            if gam_event and gam_event.get("points_awarded", 0) > 0:
                from app.sockets.events import sio, LumenEvents
                await sio.emit(
                    LumenEvents.LEADERBOARD_UPDATE,
                    {**gam_event, "user_id": str(current_user.id)},
                )
        except Exception as _gam_err:
            logger.warning("Gamification award failed (report)", extra={"error": str(_gam_err)})

    return IssueOut.model_validate(full_issue)


# ── GET /issues ───────────────────────────────────────────────

@router.get("", response_model=PaginatedIssues)
async def list_issues(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    ward: Optional[str] = Query(None),
    is_emergency: Optional[bool] = Query(None),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    db: DB = None,
):
    """Paginated issue list with optional filters. Used by public feed and admin queue."""
    result = await get_issues_paginated(
        db=db, page=page, per_page=per_page,
        status=status, category=category, severity=severity,
        ward=ward, is_emergency=is_emergency,
        sort_by=sort_by, sort_dir=sort_dir,
    )
    return PaginatedIssues(
        items=[IssueOut.model_validate(i) for i in result["items"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        pages=result["pages"],
    )


# ── GET /issues/nearby ────────────────────────────────────────
# NOTE: /nearby must be BEFORE /{issue_id} to avoid param capture

@router.get("/nearby", response_model=List[IssueOut])
async def list_issues_nearby(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius: float = Query(2000.0, ge=100, le=50000),
    limit: int = Query(50, ge=1, le=200),
    db: DB = None,
):
    """
    Issues within radius meters of (lat, lng).
    Sorted by distance asc, emergency issues first.
    Used by the map view on load and on viewport change.
    """
    issues = await get_issues_nearby(db, lat, lng, radius, limit)
    return [IssueOut.model_validate(i) for i in issues]


# ── POST /issues/check-duplicates ────────────────────────────
# NOTE: Must be BEFORE /{issue_id} — FastAPI resolves routes in registration
# order, so literal paths must precede parameterised ones.
# POST (not GET) because description can be up to 5000 chars —
# exceeds safe URL query parameter length limits in proxies.

class DuplicateCheckRequest(BaseModel):
    title: str = Field(..., min_length=5, max_length=256)
    description: str = Field(..., min_length=10, max_length=5000)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    category_id: Optional[str] = None


@router.post("/check-duplicates")
async def check_duplicates(
    payload: DuplicateCheckRequest,
    db: DB = None,
):
    """
    Pre-submit duplicate check.

    POST (not GET) because description can be up to 5000 chars —
    exceeds safe URL query parameter length limits in proxies.

    Called by `ReportIssueModal` in Step 3 before the user submits.
    Returns potential duplicate issues sorted by similarity descending.

    Frontend behaviour:
      - If `has_duplicates=True`: show `DuplicateSuggestionPanel`
        with option to "Support existing issue" or "Submit anyway".
      - If `has_duplicates=False`: proceed to submit normally.

    Body:
        title:        Report title (min 5, max 256 chars).
        description:  Report description (min 10, max 5000 chars).
        latitude:     GPS latitude of the new report.
        longitude:    GPS longitude of the new report.
        category_id:  Optional UUID string of the selected category.

    Returns:
        {
            has_duplicates: bool,
            duplicates: [{issue_id, title, status, distance_meters,
                          similarity_score, duplicate_strength, ...}],
            message: str
        }
    """
    import uuid as _uuid
    from app.services.duplicate_detector import find_duplicates

    duplicates = await find_duplicates(
        title=payload.title,
        description=payload.description,
        latitude=payload.latitude,
        longitude=payload.longitude,
        category_id=_uuid.UUID(payload.category_id) if payload.category_id else None,
        db=db,
    )

    return {
        "has_duplicates": len(duplicates) > 0,
        "duplicates": duplicates,
        "message": (
            f"Found {len(duplicates)} similar issue(s) nearby. "
            "Consider supporting an existing report instead."
            if duplicates
            else "No similar issues found nearby."
        ),
    }


# ── GET /issues/{id} ─────────────────────────────────────────

@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(issue_id: uuid.UUID, db: DB):
    """
    Full issue detail with media, status_history, verifications, comments.
    Increments view_count.
    """
    issue = await get_issue_by_id(issue_id, db, increment_view=True)
    return IssueOut.model_validate(issue)


# ── PATCH /issues/{id} ────────────────────────────────────────

@router.patch("/{issue_id}", response_model=IssueOut)
async def update_issue_endpoint(
    issue_id: uuid.UUID,
    payload: IssueUpdate,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """Update title, description, category, severity. Reporter or admin only."""
    issue = await update_issue(issue_id, payload, db, current_user)

    # Emit real-time issue_updated socket event
    updates = {}
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.severity is not None:
        updates["severity"] = payload.severity
    if payload.category_id is not None:
        from sqlalchemy import select
        from app.models import Category
        updates["category_id"] = str(payload.category_id)
        cat_result = await db.execute(
            select(Category).where(Category.id == payload.category_id)
        )
        category = cat_result.scalar_one_or_none()
        if category:
            updates["category"] = {
                "id": str(category.id),
                "name": category.name,
                "display_name": category.display_name,
                "icon": category.icon,
                "color": category.color,
            }

    if updates:
        from app.sockets.events import emit_issue_updated
        await emit_issue_updated(str(issue_id), updates)

    return IssueOut.model_validate(issue)


# ── DELETE /issues/{id} ───────────────────────────────────────

@router.delete("/{issue_id}", status_code=204)
async def delete_issue_endpoint(
    issue_id: uuid.UUID,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """Reporters close their own issue. Admins hard-delete."""
    await delete_issue(issue_id, db, current_user)
    return None


# ── PATCH /issues/{id}/status ────────────────────────────────

@router.patch("/{issue_id}/status", response_model=IssueOut)
async def change_status(
    issue_id: uuid.UUID,
    payload: StatusChangeRequest,
    db: DB = None,
    current_user: OfficialUser = None,
):
    """Change issue status. Officials and admins only. Validates transition."""
    issue, history = await change_issue_status(issue_id, payload, db, current_user)
    full_issue = await get_issue_by_id(issue_id, db)

    await emit_status_update(
        str(issue_id),
        payload.status,
        {
            "id": str(history.id),
            "from_status": history.from_status,
            "to_status": history.to_status,
            "changed_at": history.changed_at.isoformat(),
            "note": history.note,
            "is_official": history.is_official,
        },
    )

    # ── Notification dispatch ─────────────────────────────────
    try:
        from app.services.notification import (
            notify_issue_status_change,
            notify_resolution_prompt,
        )
        if full_issue.reporter_id:
            await notify_issue_status_change(
                reporter_id=str(full_issue.reporter_id),
                issue_id=str(issue_id),
                issue_title=full_issue.title,
                new_status=payload.status,
                db=db,
            )
        if payload.status == "resolved" and full_issue.reporter_id:
            await notify_resolution_prompt(
                reporter_id=str(full_issue.reporter_id),
                issue_id=str(issue_id),
                issue_title=full_issue.title,
                db=db,
            )
    except Exception as _notify_err:
        logger.warning("Notification dispatch failed", extra={"error": str(_notify_err)})

    return IssueOut.model_validate(full_issue)


# ── POST /issues/{id}/assign ─────────────────────────────────

@router.post("/{issue_id}/assign", response_model=IssueOut)
async def assign_issue(
    issue_id: uuid.UUID,
    payload: AssignRequest,
    db: DB = None,
    current_user: OfficialUser = None,
):
    """Assign issue to an official. Sets status to 'assigned'."""
    await get_issue_by_id(issue_id, db)  # existence check

    assignment = Assignment(
        issue_id=issue_id,
        assigned_to=payload.assigned_to,
        assigned_by=current_user.id,
        department=payload.department,
        due_date=payload.due_date,
        note=payload.note,
        is_active=True,
    )
    db.add(assignment)
    await db.flush()

    # Deactivate prior assignments
    await db.execute(
        sa_update(Assignment)
        .where(Assignment.issue_id == issue_id, Assignment.id != assignment.id)
        .values(is_active=False)
    )

    status_payload = StatusChangeRequest(status="assigned", note=payload.note)
    issue, history = await change_issue_status(issue_id, status_payload, db, current_user)
    issue.assigned_to = payload.assigned_to
    await db.flush()

    await emit_status_update(
        str(issue_id), "assigned",
        {"to_status": "assigned", "note": payload.note,
         "changed_at": datetime.now(timezone.utc).isoformat()},
    )

    return IssueOut.model_validate(await get_issue_by_id(issue_id, db))


# ── POST /issues/{id}/flag ───────────────────────────────────

@router.post("/{issue_id}/flag", status_code=204)
async def flag_issue(
    issue_id: uuid.UUID,
    payload: FlagCreate,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """Flag an issue for moderation. One flag per user per issue."""
    await get_issue_by_id(issue_id, db)

    existing = await db.execute(
        sa_select(Flag).where(
            Flag.issue_id == issue_id,
            Flag.flagged_by == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("You have already flagged this issue")

    db.add(Flag(
        issue_id=issue_id,
        flagged_by=current_user.id,
        reason=payload.reason,
        detail=payload.detail,
        status="pending",
    ))
    await db.flush()  # Persist flag so process_flag can count it

    # ── Moderation threshold check ─────────────────────────
    from app.services.moderation import process_flag
    moderation_result = await process_flag(
        issue_id=issue_id,
        flagged_by_id=current_user.id,
        reason=payload.reason,
        db=db,
    )

    if moderation_result["action"] == "auto_hidden":
        logger.warning(
            "Issue auto-hidden after flag threshold",
            extra={
                "issue_id": str(issue_id),
                "flag_count": moderation_result["flag_count"],
            }
        )

    return None


# ── POST /issues/{id}/verify ─────────────────────────────────

@router.post("/{issue_id}/verify", response_model=VerificationOut)
async def verify_issue(
    issue_id: uuid.UUID,
    payload: VerifyRequest,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """
    Community verification — hard or soft.

    Hard verification:
      - Requires latitude + longitude in request body
      - User must be within 100 m of the issue (settings.hard_verification_radius_meters)
      - Trust weight: 1.0  |  Points awarded: 25

    Soft verification:
      - No location required; user confirms from personal knowledge
      - Trust weight: 0.5  |  Points awarded: 10

    Auto-upgrades issue from 'reported' → 'verified' when weighted score ≥ 2.0.
    Emits `verification_update` socket event; also emits `status_update` if the
    issue status was auto-upgraded so map markers update in real time.
    """
    from app.services.verification_service import create_verification

    verification, status_upgraded = await create_verification(
        issue_id=issue_id,
        user_id=current_user.id,
        verification_type=payload.verification_type,
        user_lat=payload.latitude,
        user_lng=payload.longitude,
        comment=payload.comment,
        db=db,
    )

    # Reload issue for current verification_count after flush
    issue = await get_issue_by_id(issue_id, db)

    # Emit verification_update so connected clients refresh the count
    await emit_verification_update(
        issue_id=str(issue_id),
        verification_count=issue.verification_count,
        verification_data={
            "id": str(verification.id),
            "verification_type": verification.verification_type,
            "trust_weight": verification.trust_weight,
            "comment": verification.comment,
        },
    )

    # If status was auto-upgraded emit status_update so map markers update live
    if status_upgraded:
        await emit_status_update(
            issue_id=str(issue_id),
            new_status="verified",
            history_entry={
                "to_status": "verified",
                "is_official": False,
                "note": "Auto-verified by community",
                "changed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return VerificationOut.model_validate(verification)


# ── POST /issues/{id}/support ────────────────────────────────

@router.post("/{issue_id}/support", response_model=VoteOut)
async def support_issue(
    issue_id: uuid.UUID,
    payload: VoteCreate,
    db: DB = None,
    current_user: OptionalUser = None,
):
    """'I see this too' — one support vote per user/session. Increments vote_count."""
    issue = await get_issue_by_id(issue_id, db)
    user_id = current_user.id if current_user else None

    if user_id:
        existing = await db.execute(
            sa_select(Vote).where(
                Vote.issue_id == issue_id,
                Vote.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("You have already supported this issue")

    vote = Vote(
        issue_id=issue_id,
        user_id=user_id,
        guest_session_id=None if current_user else "guest_anonymous",
        vote_type=payload.vote_type,
        duplicate_of=payload.duplicate_of,
    )
    db.add(vote)
    issue.vote_count += 1
    await db.flush()
    return VoteOut.model_validate(vote)


# ── POST /issues/{id}/resolution-feedback ───────────────────

@router.post("/{issue_id}/resolution-feedback", response_model=ResolutionFeedbackOut)
async def resolution_feedback(
    issue_id: uuid.UUID,
    payload: ResolutionFeedbackRequest,
    db: DB = None,
    current_user: OptionalUser = None,
):
    """
    Citizen confirms or disputes a resolution.
    3+ disputes auto-reopen the issue (status → disputed).
    """
    issue = await get_issue_by_id(issue_id, db)

    if issue.status not in ("resolved", "disputed"):
        raise ValidationError("Can only submit feedback on resolved issues")

    feedback = ResolutionFeedback(
        issue_id=issue_id,
        submitted_by=current_user.id if current_user else None,
        is_resolved=payload.is_resolved,
        comment=payload.comment,
    )
    db.add(feedback)
    await db.flush()

    if not payload.is_resolved:
        dispute_count = (
            await db.execute(
                sa_select(sa_func.count(ResolutionFeedback.id)).where(
                    ResolutionFeedback.issue_id == issue_id,
                    ResolutionFeedback.is_resolved == False,
                )
            )
        ).scalar_one()

        if dispute_count >= settings.dispute_reopen_threshold:
            issue.status = "disputed"
            db.add(StatusHistory(
                issue_id=issue_id,
                from_status="resolved",
                to_status="disputed",
                changed_by=current_user.id if current_user else None,
                note=f"Auto-reopened: {dispute_count} citizens disputed the resolution.",
                is_official=False,
                is_public=True,
            ))
            feedback.dispute_triggers_reopen = True
            await db.flush()
            await emit_issue_reopened(str(issue_id), dispute_count)

    # ── Gamification: award points for confirming resolution ──
    if payload.is_resolved and current_user and not getattr(current_user, "is_guest", False):
        try:
            from app.services.gamification import award_points
            await award_points(
                user_id=current_user.id,
                action="resolve_confirmed",
                db=db,
                issue_id=issue_id,
            )
        except Exception as _gam_err:
            logger.warning("Gamification award failed (resolve)", extra={"error": str(_gam_err)})

    await emit_resolution_feedback(str(issue_id), {
        "is_resolved": payload.is_resolved,
        "comment": payload.comment,
    })
    return ResolutionFeedbackOut.model_validate(feedback)

"""
Lumen Issue Service
Business logic for issue creation, retrieval, update, and deletion.
"""
import uuid
import math
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.orm import selectinload

from app.models import (
    Issue, IssueMedia, StatusHistory, IssueAuditLog,
    Category, User, Vote, Verification,
)
from app.schemas import IssueCreate, IssueUpdate, StatusChangeRequest
from app.exceptions import NotFoundError, ForbiddenError, ValidationError
from app.config import settings
from app.logging_config import logger
from app.services.geo_utils import reverse_geocode

# ── Valid status transitions ───────────────────────────────────
VALID_TRANSITIONS = {
    "reported":    {"verified", "assigned", "in_progress", "disputed", "closed"},
    "verified":    {"assigned", "in_progress", "disputed", "closed"},
    "assigned":    {"in_progress", "resolved", "disputed", "closed"},
    "in_progress": {"resolved", "disputed", "closed"},
    "resolved":    {"disputed", "closed"},
    "disputed":    {"assigned", "in_progress", "closed"},
    "closed":      set(),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_issue_by_id(
    issue_id: uuid.UUID,
    db: AsyncSession,
    increment_view: bool = False,
) -> Issue:
    """
    Load a single issue with all relationships eagerly loaded.
    Optionally increments view_count.
    Raises NotFoundError if not found.
    """
    result = await db.execute(
        select(Issue)
        .options(
            selectinload(Issue.category),
            selectinload(Issue.reporter),
            selectinload(Issue.assignee),
            selectinload(Issue.media),
            selectinload(Issue.status_history).selectinload(StatusHistory.actor),
            selectinload(Issue.verifications),
            selectinload(Issue.comments),
        )
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue", str(issue_id))

    if increment_view:
        issue.view_count += 1
        await db.flush()

    return issue


async def get_issues_paginated(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    ward: Optional[str] = None,
    is_emergency: Optional[bool] = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
) -> dict:
    """Returns paginated issue list with optional filters."""
    query = select(Issue).options(
        selectinload(Issue.category),
        selectinload(Issue.reporter),
        selectinload(Issue.assignee),
        selectinload(Issue.media),
        selectinload(Issue.status_history),
    )

    filters = []
    if status:
        filters.append(Issue.status == status)
    if category:
        query = query.join(Category, Issue.category_id == Category.id)
        filters.append(Category.name == category)
    if severity:
        filters.append(Issue.severity == severity)
    if ward:
        filters.append(Issue.ward.ilike(f"%{ward}%"))
    if is_emergency is not None:
        filters.append(Issue.is_emergency == is_emergency)

    if filters:
        query = query.where(and_(*filters))

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Sort — emergency always first
    sort_col = getattr(Issue, sort_by, Issue.created_at)
    order = desc(sort_col) if sort_dir == "desc" else asc(sort_col)
    query = query.order_by(desc(Issue.is_emergency), order)

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    issues = (await db.execute(query)).scalars().all()

    return {
        "items": list(issues),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if total > 0 else 0,
    }


async def get_issues_nearby(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_meters: float = 2000.0,
    limit: int = 50,
) -> List[Issue]:
    """
    Returns issues within radius_meters of (lat, lng).
    Bounding box pre-filter then haversine distance sort.
    Attaches distance_meters attribute to each issue.
    """
    lat_delta = radius_meters / 111320.0
    lng_delta = radius_meters / (111320.0 * math.cos(math.radians(lat)))

    result = await db.execute(
        select(Issue)
        .options(
            selectinload(Issue.category),
            selectinload(Issue.reporter),
            selectinload(Issue.assignee),
            selectinload(Issue.media),
            selectinload(Issue.status_history),
        )
        .where(
            and_(
                Issue.latitude.between(lat - lat_delta, lat + lat_delta),
                Issue.longitude.between(lng - lng_delta, lng + lng_delta),
                Issue.status != "closed",
            )
        )
        .order_by(desc(Issue.is_emergency), desc(Issue.created_at))
        .limit(limit * 3)  # Over-fetch for haversine filter
    )
    candidates = result.scalars().all()

    R = 6371000.0

    def haversine(i: Issue) -> float:
        phi1, phi2 = math.radians(lat), math.radians(i.latitude)
        dphi = math.radians(i.latitude - lat)
        dlambda = math.radians(i.longitude - lng)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    nearby = []
    for issue in candidates:
        dist = haversine(issue)
        if dist <= radius_meters:
            issue.distance_meters = dist
            nearby.append((not issue.is_emergency, dist, issue))

    nearby.sort(key=lambda x: (x[0], x[1]))
    return [item[2] for item in nearby[:limit]]


async def create_issue(
    payload: IssueCreate,
    db: AsyncSession,
    reporter: Optional[User],
    guest_session_id: Optional[str] = None,
) -> Issue:
    """
    Creates a new issue record.
    Validates category, handles anonymous/guest identity,
    creates Issue, StatusHistory, and IssueAuditLog.
    Flushes to obtain issue.id (caller commits).
    """
    # Validate category
    if payload.category_id:
        cat_result = await db.execute(
            select(Category).where(Category.id == payload.category_id)
        )
        if not cat_result.scalar_one_or_none():
            raise ValidationError(f"Category not found: {payload.category_id}")

    # Determine reporter identity
    reporter_id = None
    is_anonymous = payload.is_anonymous

    if reporter:
        if reporter.is_guest:
            is_anonymous = True
            guest_session_id = guest_session_id or str(reporter.id)
        elif is_anonymous:
            # Store internally but mask publicly
            reporter_id = reporter.id
        else:
            reporter_id = reporter.id

    issue = Issue(
        id=uuid.uuid4(),
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        severity=payload.severity,
        status="reported",
        is_anonymous=is_anonymous,
        is_emergency=payload.is_emergency,
        reporter_id=reporter_id,
        guest_session_id=guest_session_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        address=payload.address,
        ward=payload.ward,
        offline_draft_id=payload.offline_draft_id,
        vote_count=0,
        verification_count=0,
        view_count=0,
        user_correction=False,
    )
    db.add(issue)
    await db.flush()

    # ── Auto-fill address / ward via reverse geocoding (Session 6) ──
    # Only call Nominatim when the client did not supply both values,
    # to avoid unnecessary network calls on well-formed submissions.
    if not issue.address or not issue.ward:
        try:
            geo = await reverse_geocode(issue.latitude, issue.longitude)
            if not issue.address:
                issue.address = geo["address"]
            if not issue.ward:
                issue.ward = geo["ward"]
            if not issue.ward and geo.get("zone"):
                # Fallback: use city/zone as a coarse ward substitute
                issue.ward = geo["zone"]
        except Exception as exc:
            # Non-critical — log and continue; address remains whatever the client sent
            logger.warning(
                "Reverse geocode skipped during issue creation",
                extra={"issue_id": str(issue.id), "error": str(exc)},
            )

    db.add(StatusHistory(
        issue_id=issue.id,
        from_status=None,
        to_status="reported",
        changed_by=reporter_id,
        changed_at=utcnow(),
        note="Issue reported",
        is_official=False,
        is_public=True,
    ))

    db.add(IssueAuditLog(
        issue_id=issue.id,
        actor_id=reporter_id,
        action="created",
        after_state={
            "status": "reported",
            "severity": issue.severity,
            "is_emergency": issue.is_emergency,
        },
    ))

    logger.info(
        "Issue created",
        extra={
            "issue_id": str(issue.id),
            "is_emergency": payload.is_emergency,
            "reporter_id": str(reporter_id) if reporter_id else "anonymous",
        },
    )
    return issue


async def update_issue(
    issue_id: uuid.UUID,
    payload: IssueUpdate,
    db: AsyncSession,
    current_user: User,
) -> Issue:
    """
    Update title, description, category, or severity.
    Only reporter or admin. Cannot edit resolved/closed issues.
    """
    issue = await get_issue_by_id(issue_id, db)

    if not current_user.is_admin and issue.reporter_id != current_user.id:
        raise ForbiddenError("Only the reporter or an admin can edit this issue")
    if issue.status in ("resolved", "closed"):
        raise ValidationError("Cannot edit a resolved or closed issue")

    before = {
        "title": issue.title,
        "description": issue.description,
        "severity": issue.severity,
        "category_id": str(issue.category_id) if issue.category_id else None,
    }

    if payload.title is not None:
        issue.title = payload.title
    if payload.description is not None:
        issue.description = payload.description
    if payload.category_id is not None:
        issue.category_id = payload.category_id
    if payload.severity is not None:
        issue.severity = payload.severity

    db.add(IssueAuditLog(
        issue_id=issue.id,
        actor_id=current_user.id,
        action="updated",
        before_state=before,
        after_state={"title": issue.title, "severity": issue.severity},
    ))
    await db.flush()
    return issue


async def change_issue_status(
    issue_id: uuid.UUID,
    payload: StatusChangeRequest,
    db: AsyncSession,
    current_user: User,
) -> tuple[Issue, StatusHistory]:
    """
    Changes issue status with transition validation.
    Creates StatusHistory and AuditLog. Sets resolved_at when resolved.
    Returns (issue, history_entry).
    """
    issue = await get_issue_by_id(issue_id, db)

    allowed = VALID_TRANSITIONS.get(issue.status, set())
    if payload.status not in allowed:
        raise ValidationError(
            f"Cannot transition from '{issue.status}' to '{payload.status}'. "
            f"Allowed: {sorted(allowed)}"
        )

    old_status = issue.status
    issue.status = payload.status

    if payload.status == "resolved":
        issue.resolved_at = utcnow()

    history = StatusHistory(
        issue_id=issue.id,
        from_status=old_status,
        to_status=payload.status,
        changed_by=current_user.id,
        changed_at=utcnow(),
        note=payload.note,
        is_official=current_user.is_official or current_user.is_admin,
        is_public=True,
    )
    db.add(history)

    db.add(IssueAuditLog(
        issue_id=issue.id,
        actor_id=current_user.id,
        action="status_changed",
        before_state={"status": old_status},
        after_state={"status": payload.status, "note": payload.note},
    ))
    await db.flush()

    logger.info(
        "Issue status changed",
        extra={
            "issue_id": str(issue_id),
            "from_status": old_status,
            "to_status": payload.status,
        },
    )
    return issue, history


async def delete_issue(
    issue_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> None:
    """
    Admins hard-delete. Reporters close (status=closed).
    """
    issue = await get_issue_by_id(issue_id, db)

    if not current_user.is_admin and issue.reporter_id != current_user.id:
        raise ForbiddenError("Only the reporter or an admin can delete this issue")

    if current_user.is_admin:
        await db.delete(issue)
    else:
        issue.status = "closed"
        db.add(IssueAuditLog(
            issue_id=issue.id,
            actor_id=current_user.id,
            action="closed_by_reporter",
        ))
    await db.flush()

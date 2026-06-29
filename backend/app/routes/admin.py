"""
Lumen Admin Routes
All routes require is_admin or is_official role.

GET  /admin/queue              — paginated issue queue with filters
PATCH /admin/issues/bulk       — bulk status update
GET  /admin/users              — user list with search
PATCH /admin/users/{id}/moderate — ban/unban, set official
GET  /admin/flags              — pending flags queue
PATCH /admin/flags/{id}        — review/dismiss flag
GET  /admin/export             — CSV/JSON export
"""
import uuid
import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_admin_user, get_official_or_admin, DB, AdminUser, OfficialUser
from app.models import Issue, User, Flag, Category, StatusHistory, IssueAuditLog
from app.schemas import (
    IssueOut, PaginatedIssues, StatusChangeRequest, AdminBulkUpdate,
    AdminUserModerate, FlagReviewRequest,
)
from app.services.issue_service import change_issue_status
from app.services.moderation import dismiss_flag, resolve_flag, get_moderation_queue
from app.sockets.events import emit_status_update, emit_admin_action
from app.exceptions import NotFoundError
from app.logging_config import logger

router = APIRouter()


@router.get("/queue", response_model=PaginatedIssues)
async def admin_queue(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    ward: Optional[str] = Query(None),
    is_emergency: Optional[bool] = Query(None),
    db: DB = None,
    current_user: OfficialUser = None,
):
    """
    Admin issue queue.
    Emergency issues always shown first regardless of other sort order.
    All filters are optional and combinable.
    """
    from app.services.issue_service import get_issues_paginated
    result = await get_issues_paginated(
        db=db,
        page=page,
        per_page=per_page,
        status=status,
        category=category,
        severity=severity,
        ward=ward,
        is_emergency=is_emergency,
    )
    return PaginatedIssues(
        items=[IssueOut.model_validate(i) for i in result["items"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        pages=result["pages"],
    )


@router.patch("/issues/bulk", status_code=200)
async def bulk_update_issues(
    payload: AdminBulkUpdate,
    db: DB = None,
    current_user: OfficialUser = None,
):
    """
    Bulk status update for multiple issues.
    Validates each transition and records history.
    Emits status_update socket event for each.
    """
    results = {"updated": [], "skipped": [], "errors": []}

    for issue_id in payload.issue_ids:
        try:
            issue, history = await change_issue_status(
                issue_id=issue_id,
                payload=StatusChangeRequest(status=payload.status, note=payload.note),
                db=db,
                current_user=current_user,
            )
            await emit_status_update(
                str(issue_id), payload.status,
                {"to_status": payload.status, "note": payload.note}
            )
            results["updated"].append(str(issue_id))
        except Exception as e:
            results["errors"].append({"id": str(issue_id), "error": str(e)})

    logger.info(
        "Admin bulk update",
        extra={
            "admin_id": str(current_user.id),
            "target_status": payload.status,
            "updated": len(results["updated"]),
            "errors": len(results["errors"]),
        }
    )

    return results


@router.get("/users")
async def list_users(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: DB = None,
    current_user: AdminUser = None,
):
    """Admin user list with optional search by email, username, or display name."""
    query = select(User).where(User.is_guest == False)  # noqa: E712

    if search:
        query = query.where(
            or_(
                User.email.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.display_name.ilike(f"%{search}%"),
            )
        )

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "username": u.username,
                "display_name": u.display_name,
                "is_admin": u.is_admin,
                "is_official": u.is_official,
                "is_banned": u.is_banned,
                "department": u.department,
                "points": u.points,
                "level": u.level,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.patch("/users/{user_id}/moderate")
async def moderate_user(
    user_id: uuid.UUID,
    payload: AdminUserModerate,
    db: DB = None,
    current_user: AdminUser = None,
):
    """Ban/unban user, set official status, assign department."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", str(user_id))

    if payload.is_banned is not None:
        user.is_banned = payload.is_banned
    if payload.is_official is not None:
        user.is_official = payload.is_official
    if payload.department is not None:
        user.department = payload.department

    await db.flush()
    await emit_admin_action("user_moderated", str(user_id), str(current_user.id))

    logger.info(
        "User moderated",
        extra={"admin_id": str(current_user.id), "target_user_id": str(user_id)},
    )

    return {"status": "updated", "user_id": str(user_id)}


@router.get("/flags")
async def list_flags(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: DB = None,
    current_user: AdminUser = None,
):
    """Returns pending moderation flags sorted by count."""
    return await get_moderation_queue(db, page, per_page)


@router.patch("/flags/{flag_id}")
async def review_flag(
    flag_id: uuid.UUID,
    payload: FlagReviewRequest,
    db: DB = None,
    current_user: AdminUser = None,
):
    """Review a moderation flag: 'reviewed' (action taken) or 'dismissed'."""
    if payload.status == "dismissed":
        await dismiss_flag(flag_id, current_user.id, db)
    else:
        await resolve_flag(flag_id, current_user.id, db)

    return {"status": "flag_reviewed", "flag_id": str(flag_id)}


@router.get("/export")
async def export_issues(
    format: str = Query("csv", pattern="^(csv|json)$"),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    ward: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: DB = None,
    current_user: OfficialUser = None,
):
    """
    Export issues as CSV or JSON.
    Supports date range, ward, and status filters.
    Capped at 5000 rows to avoid memory issues.
    """
    from datetime import datetime

    query = select(Issue).options(selectinload(Issue.category))

    filters = []
    if status:
        filters.append(Issue.status == status)
    if ward:
        filters.append(Issue.ward.ilike(f"%{ward}%"))
    if from_date:
        try:
            filters.append(Issue.created_at >= datetime.fromisoformat(from_date))
        except ValueError:
            pass
    if to_date:
        try:
            filters.append(Issue.created_at <= datetime.fromisoformat(to_date))
        except ValueError:
            pass

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(desc(Issue.created_at)).limit(5000)
    result = await db.execute(query)
    issues = result.scalars().all()

    if format == "json":
        import json as json_module
        data = [
            {
                "id": str(i.id),
                "title": i.title,
                "category": i.category.name if i.category else None,
                "severity": i.severity,
                "status": i.status,
                "ward": i.ward,
                "address": i.address,
                "latitude": i.latitude,
                "longitude": i.longitude,
                "vote_count": i.vote_count,
                "verification_count": i.verification_count,
                "is_emergency": i.is_emergency,
                "created_at": i.created_at.isoformat(),
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            }
            for i in issues
        ]
        return StreamingResponse(
            iter([json_module.dumps(data, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=lumen_issues.json"},
        )

    # CSV export
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Title", "Category", "Severity", "Status", "Ward",
        "Address", "Latitude", "Longitude", "Votes", "Verifications",
        "Emergency", "Created At", "Resolved At",
    ])
    for i in issues:
        writer.writerow([
            str(i.id), i.title,
            i.category.name if i.category else "",
            i.severity, i.status, i.ward or "",
            i.address or "", i.latitude, i.longitude,
            i.vote_count, i.verification_count,
            "Yes" if i.is_emergency else "No",
            i.created_at.isoformat(),
            i.resolved_at.isoformat() if i.resolved_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lumen_issues.csv"},
    )


@router.get("/escalations")
async def get_escalated_issues(
    db: DB = None,
    current_user: OfficialUser = None,
):
    """
    Returns issues that have been auto-escalated by the Escalation Agent.
    Sorted by escalation_count descending (most overdue first).
    """
    from app.models import Issue
    from sqlalchemy import select, desc

    result = await db.execute(
        select(Issue)
        .where(Issue.escalation_count > 0, Issue.status.notin_(["resolved", "closed"]))
        .order_by(desc(Issue.escalation_count), desc(Issue.escalated_at))
        .limit(50)
    )
    issues = result.scalars().all()

    return {
        "escalated_issues": [
            {
                "id": str(i.id),
                "title": i.title,
                "status": i.status,
                "severity": i.severity,
                "ward": i.ward,
                "escalation_count": i.escalation_count,
                "escalated_at": i.escalated_at.isoformat() if i.escalated_at else None,
                "created_at": i.created_at.isoformat(),
            }
            for i in issues
        ],
        "total": len(issues),
    }

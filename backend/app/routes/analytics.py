"""
Lumen Analytics Routes
GET /analytics/dashboard     — aggregate stats
GET /analytics/categories    — all active categories (used by many pages)
GET /analytics/eta/{issue_id} — estimated resolution time
GET /analytics/hotspots      — current predicted hotspots
GET /analytics/heatmap       — issue density data for map heatmap
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.dependencies import DB
from app.models import Issue, Category, PredictiveHotspot
from app.schemas import DashboardStats, ETAResponse, HotspotOut, CategoryOut
from app.exceptions import NotFoundError
from sqlalchemy import select, func, desc, and_, join
from sqlalchemy.orm import selectinload

router = APIRouter()


@router.get("/categories", response_model=list[CategoryOut])
async def get_categories(db: DB):
    """
    Returns all active categories.
    Used by ReportIssueModal, AIExplanationCard, and admin filters.
    """
    result = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.name)  # noqa: E712
    )
    return [CategoryOut.model_validate(c) for c in result.scalars().all()]


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(db: DB):
    """
    Returns aggregate stats for the impact dashboard.
    Computed fresh on each request (cache in Redis for production).
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Total issues (all time)
    total_result = await db.execute(select(func.count(Issue.id)))
    total = total_result.scalar_one()

    # Resolved this month
    resolved_this_month_result = await db.execute(
        select(func.count(Issue.id)).where(
            and_(
                Issue.status == "resolved",
                Issue.resolved_at >= month_start,
            )
        )
    )
    resolved_this_month = resolved_this_month_result.scalar_one()

    # Total resolved (all time) for resolution rate
    total_resolved_result = await db.execute(
        select(func.count(Issue.id)).where(Issue.status.in_(["resolved", "closed"]))
    )
    total_resolved = total_resolved_result.scalar_one()
    resolution_rate = round(total_resolved / total * 100, 1) if total > 0 else 0.0

    # Average resolution time in days (only for truly resolved issues)
    avg_days_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", Issue.resolved_at - Issue.created_at) / 86400
            )
        ).where(
            and_(
                Issue.status == "resolved",
                Issue.resolved_at.isnot(None),
            )
        )
    )
    avg_days_raw = avg_days_result.scalar_one()
    avg_days = round(avg_days_raw or 0.0, 1)

    # Issues by category name
    cat_result = await db.execute(
        select(Category.name, func.count(Issue.id))
        .join(Issue, Issue.category_id == Category.id)
        .group_by(Category.name)
    )
    issues_by_category = {row[0]: row[1] for row in cat_result.all()}

    # Issues by status
    status_result = await db.execute(
        select(Issue.status, func.count(Issue.id)).group_by(Issue.status)
    )
    issues_by_status = {row[0]: row[1] for row in status_result.all()}

    # Top 5 wards by issue count
    ward_result = await db.execute(
        select(Issue.ward, func.count(Issue.id).label("count"))
        .where(Issue.ward.isnot(None))
        .group_by(Issue.ward)
        .order_by(desc("count"))
        .limit(5)
    )
    top_wards = [{"ward": row[0], "count": row[1]} for row in ward_result.all()]

    return DashboardStats(
        total_issues=total,
        resolved_this_month=resolved_this_month,
        resolution_rate=resolution_rate,
        avg_resolution_days=avg_days,
        issues_by_category=issues_by_category,
        issues_by_status=issues_by_status,
        top_wards=top_wards,
    )


@router.get("/eta/{issue_id}", response_model=ETAResponse)
async def get_eta(issue_id: uuid.UUID, db: DB):
    """
    Estimates resolution time for a specific issue.
    Formula: category avg_resolution_days × severity factor × status factor.
    """
    result = await db.execute(
        select(Issue).options(selectinload(Issue.category))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue", str(issue_id))

    if issue.status in ("resolved", "closed"):
        return ETAResponse(
            issue_id=issue_id,
            estimated_days=0.0,
            estimated_resolution_date="Already resolved",
            confidence="high",
            basis="Issue is already resolved",
        )

    # Base days from category average
    base_days = issue.category.avg_resolution_days if issue.category else 7.0

    # Severity adjustment — critical issues get prioritised
    severity_factors = {"critical": 0.5, "high": 0.75, "medium": 1.0, "low": 1.5}
    severity_factor = severity_factors.get(issue.severity, 1.0)

    # Status adjustment — further along = less time remaining
    status_factors = {
        "reported": 1.0,
        "verified": 0.9,
        "assigned": 0.7,
        "in_progress": 0.4,
        "disputed": 0.6,
    }
    status_factor = status_factors.get(issue.status, 1.0)

    # Apply time already elapsed
    elapsed_days = (datetime.now(timezone.utc) - issue.created_at).total_seconds() / 86400
    estimated_remaining = max(0.5, base_days * severity_factor * status_factor - elapsed_days)
    estimated_remaining = round(estimated_remaining, 1)

    resolution_date = (
        datetime.now(timezone.utc) + timedelta(days=estimated_remaining)
    ).strftime("%B %d, %Y")

    confidence = "high" if issue.category and issue.status in ("assigned", "in_progress") else \
                 "medium" if issue.category else "low"

    basis = (
        f"Based on {issue.category.display_name} average ({base_days} days), "
        f"adjusted for {issue.severity} severity and {issue.status.replace('_', ' ')} status"
        if issue.category
        else "Based on general average — category not set"
    )

    return ETAResponse(
        issue_id=issue_id,
        estimated_days=estimated_remaining,
        estimated_resolution_date=resolution_date,
        confidence=confidence,
        basis=basis,
    )


@router.get("/hotspots", response_model=list[HotspotOut])
async def get_hotspots(
    category: Optional[str] = Query(None),
    db: DB = None,
):
    """
    Returns latest predicted hotspot clusters.
    Generated by the predictive Celery task (Session 16).
    """
    query = (
        select(PredictiveHotspot)
        .order_by(
            desc(PredictiveHotspot.generated_at),
            desc(PredictiveHotspot.confidence),
        )
        .limit(20)
    )

    if category:
        query = query.where(PredictiveHotspot.category == category)

    result = await db.execute(query)
    return [HotspotOut.model_validate(h) for h in result.scalars().all()]


@router.get("/heatmap")
async def get_heatmap(
    category: Optional[str] = Query(None),
    ward: Optional[str] = Query(None),
    db: DB = None,
):
    """
    Returns lat/lng weight points for Leaflet heatmap layer.
    Each point has a weight computed from vote count + severity.
    Capped at 500 points for performance.
    """
    query = select(
        Issue.latitude, Issue.longitude, Issue.vote_count, Issue.severity
    ).where(Issue.status.notin_(["closed"]))

    if category:
        query = (
            query
            .join(Category, Issue.category_id == Category.id)
            .where(Category.name == category)
        )
    if ward:
        query = query.where(Issue.ward.ilike(f"%{ward}%"))

    result = await db.execute(query.limit(500))
    rows = result.all()

    severity_weights = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}

    return [
        {
            "lat": row[0],
            "lng": row[1],
            "weight": min(1.0, (row[2] / 20) + severity_weights.get(row[3], 0.5)),
        }
        for row in rows
        if row[0] is not None and row[1] is not None
    ]


@router.get("/ward-report/{ward}")
async def get_ward_report(ward: str, db: DB = None):
    """
    Returns the most recent weekly ward report.
    Generated by the Ward Report Agent every Monday.
    If no report exists, returns 404.
    """
    from app.models import WardReport
    from sqlalchemy import select, desc

    result = await db.execute(
        select(WardReport)
        .where(WardReport.ward.ilike(f"%{ward}%"))
        .order_by(desc(WardReport.generated_at))
        .limit(1)
    )
    report = result.scalar_one_or_none()

    if not report:
        from app.exceptions import NotFoundError
        raise NotFoundError("Ward report", ward)

    return {
        "ward": report.ward,
        "week_start": report.week_start.isoformat(),
        "week_end": report.week_end.isoformat(),
        "headline": report.headline,
        "narrative": report.narrative,
        "key_achievements": report.key_achievements,
        "key_concerns": report.key_concerns,
        "stats": report.stats,
        "generated_at": report.generated_at.isoformat(),
        "generated_by": f"Lumen Ward Report Agent ({report.agent_model})",
    }

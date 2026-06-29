"""
Lumen Gamification Routes
GET  /gamification/leaderboard  — paginated leaderboard (all-time, monthly, weekly)
GET  /gamification/me           — current user's full gamification stats
GET  /gamification/users/{id}   — another user's public gamification profile
GET  /gamification/badges       — all available badges (catalogue)
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.dependencies import DB, get_current_user, CurrentUser
from app.schemas import LeaderboardEntry
from app.exceptions import NotFoundError
from app.logging_config import logger

router = APIRouter()


@router.get("/leaderboard")
async def get_leaderboard(
    period: str = Query("all_time", pattern="^(all_time|monthly|weekly)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=50),
    db: DB = None,
):
    """
    Returns paginated leaderboard.

    - **all_time**: sorted by total points ever
    - **monthly**: points earned in last 30 days
    - **weekly**: points earned in last 7 days

    Guest and banned users are excluded.
    """
    from app.services.gamification import get_leaderboard as _get_leaderboard
    return await _get_leaderboard(db=db, period=period, page=page, per_page=per_page)


@router.get("/me")
async def get_my_stats(
    db: DB = None,
    user=Depends(get_current_user),
):
    """Returns the authenticated user's full gamification profile."""
    from app.services.gamification import get_user_stats
    stats = await get_user_stats(user_id=user.id, db=db)
    if not stats:
        raise NotFoundError("User", str(user.id))
    return stats


@router.get("/users/{user_id}")
async def get_user_profile(
    user_id: uuid.UUID,
    db: DB = None,
):
    """
    Returns a user's public gamification profile.
    Respects privacy settings — pseudonym shown if user is anonymous.
    """
    from app.services.gamification import get_user_stats
    stats = await get_user_stats(user_id=user_id, db=db)
    if not stats:
        raise NotFoundError("User", str(user_id))
    return stats


@router.get("/badges")
async def get_badges(db: DB):
    """
    Returns the full badge catalogue with conditions shown as human-readable text.
    Used by the ProfilePage badge showcase and ReportIssueModal gamification hints.
    """
    from sqlalchemy import select
    from app.models import Badge

    result = await db.execute(select(Badge).order_by(Badge.category, Badge.name))
    badges = result.scalars().all()

    return [
        {
            "id": str(b.id),
            "name": b.name,
            "display_name": b.display_name,
            "description": b.description,
            "icon": b.icon,
            "category": b.category,
            "points_required": b.points_required,
        }
        for b in badges
    ]

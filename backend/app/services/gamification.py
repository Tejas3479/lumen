"""
Lumen Gamification Service
Points, levels, badges, streaks, and leaderboard.

Point values (configurable via env in production):
  - report_issue:          10 pts
  - verify_issue:           5 pts
  - resolve_confirmed:     25 pts  (reporter confirms it's fixed)
  - daily_streak:           3 pts / day
  - first_responder:       15 pts  (first verifier on a new issue)
  - emergency_report:      20 pts  (reporting emergency issue)

Level thresholds: 0, 100, 300, 600, 1000, 1500, 2100, …
  Level N requires N*(N+1)/2 * 100 points total.

Badge conditions checked after every point award.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.logging_config import logger


# ── Point values ──────────────────────────────────────────────
POINT_VALUES = {
    "report_issue":       10,
    "verify_issue":        5,
    "resolve_confirmed":  25,
    "daily_streak":        3,
    "first_responder":    15,
    "emergency_report":   20,
    "flag_accepted":       5,
    "comment_pinned":     10,
}

# ── Level thresholds ──────────────────────────────────────────
LEVEL_THRESHOLDS = [0, 100, 300, 700, 1500]

# level_for_points(pts): find max level where threshold ≤ pts
def level_for_points(points: int) -> int:
    """Returns the level a user should be at for their point total."""
    for level, limit in enumerate(LEVEL_THRESHOLDS, start=1):
        if points < limit:
            return level - 1
    # Fallback progression for higher levels
    return len(LEVEL_THRESHOLDS) + (points - LEVEL_THRESHOLDS[-1]) // 1000


def points_for_next_level(current_level: int) -> int:
    """Returns points needed to reach the next level."""
    if current_level < len(LEVEL_THRESHOLDS):
        return LEVEL_THRESHOLDS[current_level]
    return LEVEL_THRESHOLDS[-1] + (current_level - len(LEVEL_THRESHOLDS) + 1) * 1000


# ── Badge definitions ─────────────────────────────────────────
# badge_name → condition function(user_stats: dict) → bool
BADGE_CONDITIONS = {
    "first_report": lambda s: s.get("issues_reported", 0) >= 1,
    "reporter_5":   lambda s: s.get("issues_reported", 0) >= 5,
    "reporter_25":  lambda s: s.get("issues_reported", 0) >= 25,
    "verifier_10":  lambda s: s.get("verifications", 0) >= 10,
    "streak_7":     lambda s: s.get("streak_days", 0) >= 7,
    "streak_30":    lambda s: s.get("streak_days", 0) >= 30,
    "first_responder": lambda s: s.get("first_responder_count", 0) >= 1,
    "resolver":     lambda s: s.get("confirmed_resolved", 0) >= 5,
    "century":      lambda s: s.get("points", 0) >= 100,
    "champion":     lambda s: s.get("points", 0) >= 1000,
}


async def award_points(
    user_id: uuid.UUID,
    action: str,
    db: AsyncSession,
    issue_id: Optional[uuid.UUID] = None,
    custom_points: Optional[int] = None,
) -> dict:
    """
    Awards points to a user for a given action.
    Updates points, level, streak, and checks badge conditions.

    Returns a dict with:
      - points_awarded
      - total_points
      - new_level (if levelled up, else None)
      - badge_unlocked (dict if a badge was earned, else None)
      - streak_days
    """
    from app.models import User, LeaderboardPoints, Badge, UserBadge

    points = custom_points if custom_points is not None else POINT_VALUES.get(action, 0)
    if points == 0:
        return {"points_awarded": 0, "total_points": 0, "new_level": None, "badge_unlocked": None}

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.is_guest:
        return {"points_awarded": 0, "total_points": 0, "new_level": None, "badge_unlocked": None}

    old_level = user.level
    user.points += points

    # Recalculate level
    new_level = level_for_points(user.points)
    user.level = new_level
    levelled_up = new_level > old_level

    # Update streak (only on daily-streak action or first action of the day)
    today = date.today()
    if user.last_active_date != today:
        if user.last_active_date and (today - user.last_active_date).days == 1:
            user.streak_days += 1
        elif user.last_active_date and (today - user.last_active_date).days > 1:
            user.streak_days = 1  # Streak broken
        elif not user.last_active_date:
            user.streak_days = 1
        user.last_active_date = today

    # Log the points event
    db.add(LeaderboardPoints(
        id=uuid.uuid4(),
        user_id=user_id,
        action=action,
        points=points,
        issue_id=issue_id,
    ))

    await db.flush()

    # Check badge conditions
    badge_unlocked = await _check_badges(user, db)

    logger.info(
        "Points awarded",
        extra={
            "user_id": str(user_id),
            "action": action,
            "points": points,
            "total": user.points,
            "level": new_level,
        }
    )

    return {
        "points_awarded": points,
        "total_points": user.points,
        "new_level": new_level if levelled_up else None,
        "badge_unlocked": badge_unlocked,
        "streak_days": user.streak_days,
        "action": action,
    }


async def _check_badges(user, db: AsyncSession) -> Optional[dict]:
    """
    Checks if the user has unlocked any new badges after a points event.
    Returns the first newly unlocked badge, or None.
    """
    from app.models import Badge, UserBadge

    # Build user stats dict for condition evaluation
    from sqlalchemy import select, func
    from app.models import Issue, Verification, LeaderboardPoints

    issues_count_result = await db.execute(
        select(func.count()).select_from(Issue).where(Issue.reporter_id == user.id)
    )
    verif_count_result = await db.execute(
        select(func.count()).select_from(Verification).where(Verification.user_id == user.id)
    )
    first_responder_result = await db.execute(
        select(func.count()).select_from(LeaderboardPoints).where(
            LeaderboardPoints.user_id == user.id,
            LeaderboardPoints.action == "first_responder",
        )
    )
    resolved_result = await db.execute(
        select(func.count()).select_from(LeaderboardPoints).where(
            LeaderboardPoints.user_id == user.id,
            LeaderboardPoints.action == "resolve_confirmed",
        )
    )

    stats = {
        "issues_reported":    issues_count_result.scalar_one(),
        "verifications":      verif_count_result.scalar_one(),
        "first_responder_count": first_responder_result.scalar_one(),
        "confirmed_resolved": resolved_result.scalar_one(),
        "streak_days":        user.streak_days,
        "points":             user.points,
    }

    # Get badges the user already has
    existing_result = await db.execute(
        select(UserBadge.badge_id).where(UserBadge.user_id == user.id)
    )
    existing_badge_ids = {row[0] for row in existing_result.all()}

    # Load all badges
    badges_result = await db.execute(select(Badge))
    all_badges = badges_result.scalars().all()

    for badge in all_badges:
        if badge.id in existing_badge_ids:
            continue
        condition = BADGE_CONDITIONS.get(badge.name)
        if condition and condition(stats):
            # Award the badge
            db.add(UserBadge(
                id=uuid.uuid4(),
                user_id=user.id,
                badge_id=badge.id,
            ))
            await db.flush()
            logger.info(
                "Badge unlocked",
                extra={"user_id": str(user.id), "badge": badge.name},
            )
            return {
                "id": str(badge.id),
                "name": badge.name,
                "display_name": badge.display_name,
                "description": badge.description,
                "icon": badge.icon,
                "category": badge.category,
            }

    return None


async def get_leaderboard(
    db: AsyncSession,
    period: str = "all_time",
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """
    Returns paginated leaderboard entries.
    Periods: all_time | monthly | weekly
    """
    from app.models import User, UserBadge, Issue, Verification
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    if period == "weekly":
        cutoff = now - timedelta(days=7)
    elif period == "monthly":
        cutoff = now - timedelta(days=30)
    else:
        cutoff = None

    # For time-limited periods, use points log to sum points in window
    if cutoff:
        from app.models import LeaderboardPoints
        from sqlalchemy import and_
        subq = (
            select(
                LeaderboardPoints.user_id,
                func.sum(LeaderboardPoints.points).label("period_points"),
            )
            .where(LeaderboardPoints.created_at >= cutoff)
            .group_by(LeaderboardPoints.user_id)
            .subquery()
        )
        query = (
            select(User, subq.c.period_points)
            .join(subq, User.id == subq.c.user_id)
            .where(User.is_guest == False, User.is_banned == False)  # noqa: E712
            .order_by(subq.c.period_points.desc())
        )
    else:
        query = (
            select(User)
            .where(User.is_guest == False, User.is_banned == False)  # noqa: E712
            .order_by(User.points.desc())
        )

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    paginated = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(paginated)
    rows = result.all()

    entries = []
    for rank_offset, row in enumerate(rows, start=(page - 1) * per_page + 1):
        if cutoff:
            user, period_points = row
        else:
            user = row[0]
            period_points = user.points

        # Badge count
        badge_count_result = await db.execute(
            select(func.count(UserBadge.id)).where(UserBadge.user_id == user.id)
        )
        badge_count = badge_count_result.scalar_one()

        # Issues resolved count (reporter whose issues got resolved)
        resolved_result = await db.execute(
            select(func.count(Issue.id)).where(
                Issue.reporter_id == user.id,
                Issue.status == "resolved",
            )
        )
        resolved_count = resolved_result.scalar_one()

        entries.append({
            "rank": rank_offset,
            "user_id": str(user.id),
            "display_name": user.display_name,
            "pseudonym": user.pseudonym,
            "points": period_points,
            "level": user.level,
            "badge_count": badge_count,
            "issues_resolved_count": resolved_count,
            "streak_days": user.streak_days,
        })

    return {
        "items": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-total // per_page)),  # ceiling division
        "period": period,
    }


async def get_user_stats(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """
    Returns full gamification stats for a user's profile page.
    """
    from app.models import User, Issue, Verification, UserBadge, Badge, LeaderboardPoints
    from sqlalchemy import and_

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {}

    # Counts
    issues_result = await db.execute(
        select(func.count(Issue.id)).where(Issue.reporter_id == user_id)
    )
    verif_result = await db.execute(
        select(func.count(Verification.id)).where(Verification.user_id == user_id)
    )
    resolved_result = await db.execute(
        select(func.count(Issue.id)).where(
            Issue.reporter_id == user_id,
            Issue.status.in_(["resolved", "closed"]),
        )
    )
    badge_result = await db.execute(
        select(UserBadge, Badge)
        .join(Badge, UserBadge.badge_id == Badge.id)
        .where(UserBadge.user_id == user_id)
        .order_by(UserBadge.earned_at.desc())
    )
    badges = [
        {
            "badge": {
                "id": str(b.id),
                "name": b.name,
                "display_name": b.display_name,
                "description": b.description,
                "icon": b.icon,
                "category": b.category,
            },
            "earned_at": ub.earned_at.isoformat(),
        }
        for ub, b in badge_result.all()
    ]

    # Points to next level
    pts_next = points_for_next_level(user.level)

    return {
        "user_id": str(user_id),
        "display_name": user.display_name,
        "pseudonym": user.pseudonym,
        "points": user.points,
        "level": user.level,
        "points_to_next_level": max(0, pts_next - user.points),
        "streak_days": user.streak_days,
        "issues_reported": issues_result.scalar_one(),
        "verifications": verif_result.scalar_one(),
        "issues_resolved": resolved_result.scalar_one(),
        "badges": badges,
    }

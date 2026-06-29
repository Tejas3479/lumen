"""
Lumen Verification Service
Handles hard and soft community verification.

Hard verification:
  - User must be physically present within 100m of the issue
  - GPS coordinates submitted with the request are checked with is_within_radius
  - Trust weight: 1.0
  - Points awarded: 25

Soft verification:
  - User confirms from personal knowledge (memory, regular commute)
  - No proximity check required
  - Trust weight: 0.5
  - Points awarded: 10

Auto-status-upgrade:
  - When weighted_verification_score >= 2.0 AND status == 'reported':
    → status automatically transitions to 'verified'
  - weighted_score = sum(trust_weight for each verification on this issue)
    e.g. 2 hard verifications = 2.0, OR 4 soft = 2.0, OR 1 hard + 2 soft = 2.0

Why a weighted score rather than a raw count:
  Hard verifications require GPS presence — they are harder to fake and carry more
  evidential weight than soft confirmations. Separating trust_weight from type lets
  us add more verification modes later (e.g., photographic re-verification = 0.8)
  without touching the auto-upgrade threshold logic.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import (
    Issue, Verification, StatusHistory, IssueAuditLog,
)
from app.services.geo_utils import is_within_radius
from app.config import settings
from app.logging_config import logger

# ── Thresholds ────────────────────────────────────────────────
WEIGHTED_SCORE_FOR_VERIFIED: float = 2.0
HARD_VERIFICATION_TRUST_WEIGHT: float = 1.0
SOFT_VERIFICATION_TRUST_WEIGHT: float = 0.5
HARD_VERIFICATION_POINTS: int = 25
SOFT_VERIFICATION_POINTS: int = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_verification(
    issue_id: uuid.UUID,
    user_id: uuid.UUID,
    verification_type: str,
    user_lat: Optional[float],
    user_lng: Optional[float],
    comment: Optional[str],
    db: AsyncSession,
) -> tuple[Verification, bool]:
    """
    Creates a community verification for an issue.

    Pipeline:
      1. Load issue — 404 if not found
      2. Guard: terminal-state issues cannot be verified
      3. Guard: reporter cannot verify their own issue (prevents self-inflation)
      4. Guard: one verification per user per issue
      5. For hard verification: proximity check with is_within_radius
      6. Create Verification record + increment issue.verification_count
      7. Compute cumulative weighted score → auto-upgrade to 'verified' if ≥ 2.0
      8. Award gamification points to LeaderboardPoints + User.points

    Args:
        issue_id:          UUID of the issue being verified.
        user_id:           UUID of the verifying user.
        verification_type: 'hard' or 'soft'.
        user_lat:          User's GPS latitude (required for hard).
        user_lng:          User's GPS longitude (required for hard).
        comment:           Optional text comment from the verifier.
        db:                Async SQLAlchemy session (caller commits).

    Returns:
        (Verification ORM instance, status_upgraded: bool)
        status_upgraded=True means the issue was automatically moved to 'verified'.

    Raises:
        NotFoundError:  Issue not found.
        ValidationError: Hard verification but GPS absent or user too far.
        ForbiddenError:  Reporter trying to verify own issue.
        ConflictError:   User has already verified this issue.
        ValidationError: Issue is in a terminal state (resolved/closed).
    """
    from app.exceptions import NotFoundError, ValidationError, ConflictError, ForbiddenError

    # ── Load issue ────────────────────────────────────────────
    issue_result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = issue_result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue", str(issue_id))

    # ── Guard: terminal status ────────────────────────────────
    if issue.status in ("resolved", "closed"):
        raise ValidationError("Cannot verify a resolved or closed issue")

    # ── Guard: no self-verification ───────────────────────────
    if issue.reporter_id == user_id:
        raise ForbiddenError("You cannot verify your own report")

    # ── Guard: one verification per user ──────────────────────
    existing_result = await db.execute(
        select(Verification).where(
            Verification.issue_id == issue_id,
            Verification.user_id == user_id,
        )
    )
    if existing_result.scalar_one_or_none():
        raise ConflictError("You have already verified this issue")

    # ── Hard verification: proximity check ────────────────────
    distance_meters: Optional[float] = None
    trust_weight = SOFT_VERIFICATION_TRUST_WEIGHT

    if verification_type == "hard":
        if user_lat is None or user_lng is None:
            raise ValidationError(
                "Hard verification requires your current GPS location. "
                "Please enable location access or choose 'I know this exists' instead."
            )

        within, distance_meters = is_within_radius(
            user_lat, user_lng,
            issue.latitude, issue.longitude,
            settings.hard_verification_radius_meters,
        )

        if not within:
            raise ValidationError(
                f"You appear to be {round(distance_meters)}m from this issue. "
                f"Hard verification requires being within "
                f"{int(settings.hard_verification_radius_meters)}m. "
                "Choose 'I know this exists' for soft verification instead."
            )

        trust_weight = HARD_VERIFICATION_TRUST_WEIGHT

    # ── Create verification record ────────────────────────────
    verification = Verification(
        issue_id=issue_id,
        user_id=user_id,
        verification_type=verification_type,
        distance_meters=round(distance_meters, 1) if distance_meters is not None else None,
        latitude=user_lat,
        longitude=user_lng,
        comment=comment,
        trust_weight=trust_weight,
    )
    db.add(verification)

    # Increment denormalized counter immediately
    issue.verification_count = (issue.verification_count or 0) + 1

    # ── Auto-upgrade: compute cumulative weighted score ───────
    # Query the sum of existing verifications first (before the new one is flushed)
    score_result = await db.execute(
        select(func.sum(Verification.trust_weight)).where(
            Verification.issue_id == issue_id
        )
    )
    existing_score: float = score_result.scalar_one() or 0.0
    total_score = existing_score + trust_weight  # Include the new verification

    status_upgraded = False
    if issue.status == "reported" and total_score >= WEIGHTED_SCORE_FOR_VERIFIED:
        old_status = issue.status
        issue.status = "verified"

        db.add(StatusHistory(
            issue_id=issue_id,
            from_status=old_status,
            to_status="verified",
            changed_by=user_id,
            changed_at=_utcnow(),
            note=(
                f"Auto-verified: weighted score {round(total_score, 1)} "
                f">= {WEIGHTED_SCORE_FOR_VERIFIED}"
            ),
            is_official=False,
            is_public=True,
        ))
        db.add(IssueAuditLog(
            issue_id=issue_id,
            actor_id=user_id,
            action="auto_verified",
            before_state={"status": old_status},
            after_state={
                "status": "verified",
                "weighted_score": round(total_score, 1),
            },
        ))
        status_upgraded = True
        logger.info(
            "Issue auto-verified",
            extra={
                "issue_id": str(issue_id),
                "weighted_score": round(total_score, 1),
            }
        )

    # ── Award points through centralized gamification engine ─────────
    from app.services.gamification import award_points
    points = HARD_VERIFICATION_POINTS if verification_type == "hard" else SOFT_VERIFICATION_POINTS
    gam_event = await award_points(
        user_id=user_id,
        action="verified",
        db=db,
        issue_id=issue_id,
        custom_points=points,
    )

    # Publish gamification event to socket via Redis
    from app.sockets.events import publish_to_socket
    from app.config import settings as _settings
    if gam_event and gam_event.get("points_awarded", 0) > 0:
        publish_to_socket(
            _settings.redis_url,
            "gamification_event",
            {**gam_event, "user_id": str(user_id)},
        )

    await db.flush()  # Assign IDs before returning

    logger.info(
        "Verification created",
        extra={
            "issue_id": str(issue_id),
            "user_id": str(user_id),
            "type": verification_type,
            "trust_weight": trust_weight,
            "total_weighted_score": round(total_score, 1),
            "status_upgraded": status_upgraded,
            "points_awarded": points,
        }
    )

    return verification, status_upgraded

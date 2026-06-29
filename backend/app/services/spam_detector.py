"""
Lumen Spam Detector
Full implementation with a 3-stage pipeline:

  Stage 1 — Text quality checks (synchronous, fast):
    - Description and title minimum length
    - Minimum word count (too-few words = low effort)
    - All-caps ratio (shouting detection > 70% uppercase)
    - Repetitive character sequences ("aaaaaaaaa", "!!!!!!!")
    - Profanity guard (minimal civic-context blocklist)
    - Placeholder/test-phrase detection ("test", "lorem ipsum", etc.)

  Stage 2 — Rate limiting (async DB query, fast with indexes):
    - Per-user hourly limit (default: 50 reports/hour from settings)
    - Per-user burst limit (default: 5 reports in any 10-minute window)
    - Skipped for guests and admins

  Stage 3 — Image blur detection (async, only when image path provided):
    - Uses Laplacian variance via check_image_blur (Session 5)
    - Blurry images do NOT block submission in MVP (soft signal)
    - Logged for future account-level accumulation

Returns:
    (is_spam: bool, confidence: float, reason: str)
    is_spam=True  → caller raises SpamDetectedError (HTTP 400)
    is_spam=False, confidence > 0.4 → auto-flag for admin review (non-blocking)
    is_spam=False, confidence == 0.0 → clean, proceed normally
"""
import re
from typing import Optional, Tuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import settings
from app.logging_config import logger

# ── Profanity blocklist (minimal civic-context list) ─────────
# In production, replace with a full blocklist library (e.g., better-profanity).
_BLOCKED_TERMS: frozenset = frozenset([
    "fuck", "shit", "bitch", "cunt", "bastard",
    "asshole", "damn you", "idiot", "stupid",
])

# ── Thresholds ────────────────────────────────────────────────
ALL_CAPS_THRESHOLD: float = 0.70    # > 70 % uppercase → shouting
MIN_WORD_COUNT: int = 4             # Combined title + description
BLUR_VARIANCE_THRESHOLD: float = 80.0  # Laplacian variance below this → blurry

# ── Rate limits (pulled from settings so they're env-overridable) ──
RATE_LIMIT_USER_PER_HOUR: int = settings.rate_limit_user_per_hour        # default 50
RATE_LIMIT_ANON_PER_HOUR: int = settings.rate_limit_anonymous_per_hour   # default 10
BURST_LIMIT_10_MIN: int = 5  # Max 5 reports in any 10-minute window


def _check_text_quality(title: str, description: str) -> Tuple[bool, float, str]:
    """
    Synchronous text quality checks — runs before any DB or async I/O.
    Fail-fast: returns on the first failed check.

    Args:
        title:       Issue title from the submit form.
        description: Issue description from the submit form.

    Returns:
        (is_spam, confidence, reason)
    """
    stripped_title = title.strip()
    stripped_desc = description.strip()
    combined = f"{stripped_title} {stripped_desc}"

    # ── Hard length minimums ────────────────────────────────
    if len(stripped_desc) < 10:
        return True, 1.0, "Description too short (minimum 10 characters)"

    if len(stripped_title) < 5:
        return True, 1.0, "Title too short (minimum 5 characters)"

    # ── Word count ──────────────────────────────────────────
    word_count = len(combined.split())
    if word_count < MIN_WORD_COUNT:
        return True, 0.9, (
            f"Too few words ({word_count}). "
            "Please describe the issue in more detail."
        )

    # ── All-caps detection ──────────────────────────────────
    # Only fires when text is long enough to distinguish from acronyms
    if len(combined) > 20:
        alpha_chars = [c for c in combined if c.isalpha()]
        if alpha_chars:
            caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if caps_ratio > ALL_CAPS_THRESHOLD:
                return True, 0.85, (
                    "Report appears to be shouting (excessive capitals). "
                    "Please use normal sentence case."
                )

    # ── Repetitive characters ───────────────────────────────
    # Detects "aaaaaaaaa" or "!!!!!!!!!!" (9+ repetitions of any character)
    if re.search(r"(.)\1{8,}", combined):
        return True, 0.9, (
            "Report contains repetitive characters — "
            "please describe the issue normally."
        )

    # ── Profanity guard ─────────────────────────────────────
    lowered = combined.lower()
    for term in _BLOCKED_TERMS:
        if term in lowered:
            return True, 0.95, (
                "Report contains inappropriate language. "
                "Please describe the issue professionally."
            )

    # ── Placeholder / test phrase detection ─────────────────
    # Exact-match only to avoid false positives on real reports
    _TEST_PHRASES = frozenset([
        "test", "testing", "hello world", "asdf", "qwerty",
        "lorem ipsum", "sample", "dummy", "fake report", "xyz",
        "aaa", "abc", "123",
    ])
    if combined.lower().strip() in _TEST_PHRASES:
        return True, 1.0, "Report appears to be a test submission"

    return False, 0.0, ""


async def _check_rate_limit_user(
    user,  # User model instance
    db: AsyncSession,
) -> Tuple[bool, float, str]:
    """
    Checks per-user rate limits using DB aggregates.
    Two windows: hourly ceiling and 10-minute burst ceiling.

    Skipped for: guest users, admin users.

    Args:
        user: The authenticated User ORM object.
        db:   Async SQLAlchemy session.

    Returns:
        (is_spam, confidence, reason)
    """
    from app.models import Issue

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    ten_min_ago = now - timedelta(minutes=10)

    # ── Hourly ceiling ──────────────────────────────────────
    hourly_result = await db.execute(
        select(func.count(Issue.id)).where(
            Issue.reporter_id == user.id,
            Issue.created_at >= one_hour_ago,
        )
    )
    hourly_count = hourly_result.scalar_one()

    if hourly_count >= RATE_LIMIT_USER_PER_HOUR:
        logger.warning(
            "Hourly rate limit exceeded",
            extra={
                "user_id": str(user.id),
                "count": hourly_count,
                "limit": RATE_LIMIT_USER_PER_HOUR,
            }
        )
        return True, 1.0, (
            f"Rate limit reached: you have submitted {hourly_count} reports "
            f"in the past hour. Please wait before submitting more."
        )

    # ── Burst ceiling (10-minute window) ────────────────────
    burst_result = await db.execute(
        select(func.count(Issue.id)).where(
            Issue.reporter_id == user.id,
            Issue.created_at >= ten_min_ago,
        )
    )
    burst_count = burst_result.scalar_one()

    if burst_count >= BURST_LIMIT_10_MIN:
        logger.warning(
            "Burst rate limit exceeded",
            extra={
                "user_id": str(user.id),
                "count": burst_count,
                "window_minutes": 10,
            }
        )
        return True, 0.9, (
            f"You have submitted {burst_count} reports in the last 10 minutes. "
            "Please slow down — this helps us process reports accurately."
        )

    return False, 0.0, ""


async def _check_blur(image_path: Optional[str]) -> Tuple[bool, float, str]:
    """
    Checks whether the uploaded image is too blurry to be useful.
    Returns a soft signal — does NOT block submission in MVP.

    Args:
        image_path: Relative path within settings.media_path, or None.

    Returns:
        (is_blurry: bool, blur_confidence: float, reason: str)
        blur_confidence is in [0, 1] (higher → blurrier).
    """
    if not image_path:
        return False, 0.0, ""

    full_path = Path(settings.media_path) / image_path
    if not full_path.exists():
        # Path doesn't exist yet — file may not have been flushed yet; skip
        return False, 0.0, ""

    from app.utils.image_processing import check_image_blur

    is_blurry, variance = await check_image_blur(full_path)

    if is_blurry:
        # Confidence: 1.0 when variance=0, approaching 0.0 as variance→threshold
        blur_confidence = round(
            max(0.0, 1.0 - (variance / BLUR_VARIANCE_THRESHOLD)), 2
        )
        reason = (
            f"The uploaded photo appears too blurry to be useful "
            f"(clarity score: {round(variance, 1)}, minimum needed: {BLUR_VARIANCE_THRESHOLD}). "
            "A clearer photo helps officials verify and prioritise the issue faster."
        )
        logger.info(
            "Blurry image detected (soft signal)",
            extra={
                "image_path": image_path,
                "variance": round(variance, 2),
                "blur_confidence": blur_confidence,
            }
        )
        return True, blur_confidence, reason

    return False, 0.0, ""


async def check_spam(
    title: str,
    description: str,
    reporter,  # User | None
    db: AsyncSession,
    image_path: Optional[str] = None,
) -> Tuple[bool, float, str]:
    """
    Main spam check pipeline. Called from POST /issues before issue creation.

    Pipeline order (fail-fast — exits on first hard rejection):
      1. Text quality checks (synchronous, no I/O)
      2. Rate limit check (async DB query; skipped for guests + admins)
      3. Image blur check (async, soft signal only — never blocks submission)

    Args:
        title:       Issue title.
        description: Issue description.
        reporter:    Authenticated User ORM object, or None for anonymous.
        db:          Async SQLAlchemy session.
        image_path:  Optional relative path to uploaded image for blur check.

    Returns:
        (is_spam: bool, confidence: float, reason: str)
          is_spam=True        → route raises SpamDetectedError (HTTP 400)
          is_spam=False,
            confidence > 0.4  → route should auto-flag for human review (non-blocking)
            confidence == 0.0 → clean, submit normally
    """
    # ── Stage 1: Text quality (fast, synchronous) ───────────
    is_spam, confidence, reason = _check_text_quality(title, description)
    if is_spam:
        logger.info(
            "Spam detected (text quality)",
            extra={
                "reason": reason,
                "confidence": confidence,
            }
        )
        return True, confidence, reason

    # ── Stage 2: Rate limiting (skips guests and admins) ────
    if reporter and not getattr(reporter, "is_guest", False) and not getattr(reporter, "is_admin", False):
        is_spam, confidence, reason = await _check_rate_limit_user(reporter, db)
        if is_spam:
            return True, confidence, reason

    # ── Stage 3: Image blur (soft signal — never blocks) ────
    if image_path:
        is_blurry, blur_confidence, blur_reason = await _check_blur(image_path)
        if is_blurry:
            # Blur is a soft signal: submission proceeds but gets flagged for review
            return False, blur_confidence, blur_reason

    return False, 0.0, ""

"""
Lumen Auth Routes

POST /auth/register         — create new citizen account
POST /auth/login            — authenticate with email + password
POST /auth/guest            — create guest session (no account needed)
POST /auth/logout           — stateless: client discards JWT; logged for audit
GET  /auth/me               — get current authenticated user's full profile
GET  /users/me/settings     — get full profile + preferences
PATCH /users/me/settings    — update display_name, pseudonym, prefs
"""
from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, DB
from app.schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    GuestSessionResponse,
    UserMe,
    UserSettingsUpdate,
)
from app.services.auth_service import register_user, login_user, create_guest_session
from app.logging_config import logger

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, db: DB):
    """
    Register a new citizen account.

    - **email**: unique email address
    - **password**: minimum 8 chars, must contain at least one digit
    - **username**: 3–64 chars, must be unique across all users
    - **display_name**: public-facing name shown on the map

    Returns a JWT access token and the new user's profile.

    Raises:
    - **409 CONFLICT** if email or username is already taken
    - **422 UNPROCESSABLE** if payload fails validation
    """
    user, token = await register_user(
        email=payload.email,
        password=payload.password,
        username=payload.username,
        display_name=payload.display_name,
        db=db,
    )
    return TokenResponse(access_token=token, user=UserMe.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DB):
    """
    Authenticate with email + password.

    Returns a JWT access token and the user's full profile.

    Raises:
    - **401 UNAUTHORIZED** on invalid credentials
    - **401 UNAUTHORIZED** if the account is banned
    """
    user, token = await login_user(
        email=payload.email,
        password=payload.password,
        db=db,
    )
    return TokenResponse(access_token=token, user=UserMe.model_validate(user))


@router.post("/guest", response_model=GuestSessionResponse)
async def guest_session(db: DB):
    """
    Create a guest session without an account.

    Guests can:
    - Report issues (attributed to their ephemeral session)
    - Vote and verify (with lower trust weight)

    Guests cannot:
    - Accumulate points across sessions
    - Access profile or leaderboard

    Returns a **guest_session_id** (stored client-side for offline sync)
    and a **JWT** that authenticates subsequent requests for this session.
    """
    guest_session_id, guest_user, token = await create_guest_session(db)
    return GuestSessionResponse(
        guest_session_id=guest_session_id,
        access_token=token,
        token_type="bearer",
        message="Guest session created. You can report issues without an account.",
    )


@router.post("/logout", status_code=204)
async def logout(user=Depends(get_current_user)):
    """
    Logout is stateless — the client simply discards the JWT.

    This endpoint exists for:
    - Server-side audit logging
    - Future token blacklisting support (Redis-based)
    - Triggering any session cleanup hooks

    Returns **204 No Content** on success.
    """
    logger.info("User logged out", extra={"user_id": str(user.id)})
    return None


@router.post("/users/me/fcm-token", status_code=204)
async def register_fcm_token(
    payload: dict,
    db: DB,
    user=Depends(get_current_user),
):
    """
    Stores FCM registration token for push notifications.
    Called by frontend after FCM token is obtained from Firebase JS SDK.
    """
    fcm_token = payload.get("fcm_token")
    if fcm_token:
        user.fcm_token = fcm_token
        await db.flush()
    return None


@router.get("/me", response_model=UserMe)
async def get_me(user=Depends(get_current_user)):
    """
    Returns the current authenticated user's full profile.

    Used by the frontend on app load to restore session state
    (confirm token still valid, refresh user data).

    Raises:
    - **401 UNAUTHORIZED** if no valid JWT is provided
    """
    return UserMe.model_validate(user)


@router.get("/me/settings", response_model=UserMe)
async def get_settings(user=Depends(get_current_user)):
    """
    Returns current user's full profile including notification and privacy settings.
    Mounted at both /auth/me/settings and /users/me/settings.
    """
    return UserMe.model_validate(user)


@router.patch("/me/settings", response_model=UserMe)
async def update_settings(
    payload: UserSettingsUpdate,
    db: DB = None,
    user=Depends(get_current_user),
):
    """
    Updates display_name, pseudonym, anonymous default, privacy settings,
    and notification preferences. All fields are optional.

    Used by the frontend Settings panel to persist user preferences including
    push notification subscriptions and privacy toggles.
    """
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.pseudonym is not None:
        user.pseudonym = payload.pseudonym
    if payload.is_anonymous_default is not None:
        user.is_anonymous_default = payload.is_anonymous_default
    if payload.privacy_settings is not None:
        user.privacy_settings = {**(user.privacy_settings or {}), **payload.privacy_settings}
    if payload.notification_preferences is not None:
        user.notification_preferences = {
            **(user.notification_preferences or {}),
            **payload.notification_preferences,
        }
    await db.flush()
    logger.info("User settings updated", extra={"user_id": str(user.id)})
    return UserMe.model_validate(user)


# ── DELETE /users/me ──────────────────────────────────────────

@router.delete("/me", status_code=204, tags=["privacy"])
async def delete_my_account(
    db: DB = None,
    user=Depends(get_current_user),
):
    """
    Permanently deletes the user's account and all personal data.
    DPDP Act (India, 2023) compliance: right to erasure.

    What is anonymized (community data preserved, identity removed):
      - Issues: reporter_id → null, is_anonymous → True
      - Comments: content → "[deleted]", is_deleted → True
      - Status history: changed_by → null
      - Audit log: actor_id → null

    What is deleted (purely personal records):
      - Verification records
      - LeaderboardPoints
      - UserBadge
      - Vote records
      - Flag records
      - User row itself
    """
    from app.models import (
        Comment, Verification, LeaderboardPoints, UserBadge,
        Issue, StatusHistory, IssueAuditLog, Vote, Flag,
    )
    from sqlalchemy import update as sa_update, delete as sa_delete

    user_id = user.id

    # ── Anonymize: preserve community data, remove identity ────
    await db.execute(
        sa_update(Issue)
        .where(Issue.reporter_id == user_id)
        .values(reporter_id=None, is_anonymous=True)
    )
    await db.execute(
        sa_update(Comment)
        .where(Comment.user_id == user_id)
        .values(content="[This comment was deleted by the user]", is_deleted=True)
    )
    await db.execute(
        sa_update(StatusHistory)
        .where(StatusHistory.changed_by == user_id)
        .values(changed_by=None)
    )
    await db.execute(
        sa_update(IssueAuditLog)
        .where(IssueAuditLog.actor_id == user_id)
        .values(actor_id=None)
    )

    # ── Delete: purely personal activity records ───────────────
    await db.execute(sa_delete(Verification).where(Verification.user_id == user_id))
    await db.execute(sa_delete(LeaderboardPoints).where(LeaderboardPoints.user_id == user_id))
    await db.execute(sa_delete(UserBadge).where(UserBadge.user_id == user_id))
    await db.execute(sa_delete(Vote).where(Vote.user_id == user_id))
    await db.execute(sa_delete(Flag).where(Flag.flagged_by == user_id))

    # ── Delete user record ─────────────────────────────────────
    await db.delete(user)
    await db.flush()

    logger.info("User account deleted (DPDP erasure)", extra={"user_id": str(user_id)})
    return None


# ── GET /users/me/download ────────────────────────────────────

@router.get("/me/download", tags=["privacy"])
async def download_my_data(
    db: DB = None,
    user=Depends(get_current_user),
):
    """
    Returns all personal data for the current user as a JSON export.
    DPDP Act (India, 2023) compliance: right to data portability.

    Includes: profile, reported issues, comments, verifications, points log.
    """
    from datetime import datetime, timezone
    from app.models import Issue, Comment, Verification, LeaderboardPoints
    from sqlalchemy import select

    issues_result = await db.execute(
        select(Issue).where(Issue.reporter_id == user.id)
    )
    issues = issues_result.scalars().all()

    comments_result = await db.execute(
        select(Comment).where(
            Comment.user_id == user.id,
            Comment.is_deleted == False,  # noqa: E712
        )
    )
    comments = comments_result.scalars().all()

    verifications_result = await db.execute(
        select(Verification).where(Verification.user_id == user.id)
    )
    verifications = verifications_result.scalars().all()

    points_result = await db.execute(
        select(LeaderboardPoints).where(LeaderboardPoints.user_id == user.id)
    )
    points_log = points_result.scalars().all()

    return {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat(),
            "points": user.points,
            "level": user.level,
            "streak_days": user.streak_days,
        },
        "issues_reported": [
            {
                "id": str(i.id),
                "title": i.title,
                "status": i.status,
                "severity": i.severity,
                "latitude": i.latitude,
                "longitude": i.longitude,
                "created_at": i.created_at.isoformat(),
            }
            for i in issues
        ],
        "comments": [
            {
                "id": str(c.id),
                "issue_id": str(c.issue_id),
                "content": c.content,
                "created_at": c.created_at.isoformat(),
            }
            for c in comments
        ],
        "verifications": [
            {
                "issue_id": str(v.issue_id),
                "type": v.verification_type,
                "trust_weight": v.trust_weight,
                "at": v.created_at.isoformat(),
            }
            for v in verifications
        ],
        "points_log": [
            {
                "action": p.action,
                "points": p.points,
                "issue_id": str(p.issue_id) if p.issue_id else None,
                "at": p.created_at.isoformat(),
            }
            for p in points_log
        ],
    }

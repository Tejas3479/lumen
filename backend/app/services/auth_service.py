"""
Lumen Auth Service
JWT creation, verification, password hashing, guest session management.
"""
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models import User
from app.exceptions import UnauthorizedError, ConflictError
from app.logging_config import logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password Utilities ────────────────────────────────────────

def hash_password(password: str) -> str:
    """Bcrypt-hash a plaintext password."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT Utilities ─────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    """
    Creates a signed JWT token.
    Payload: sub (user_id as string), iat, exp.
    Algorithm and secret are read from settings.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """
    Decodes and validates a JWT.
    Raises UnauthorizedError on failure (expired, tampered, malformed).
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as exc:
        raise UnauthorizedError(f"Invalid or expired token: {exc}") from exc


# ── Auth Flows ────────────────────────────────────────────────

async def register_user(
    email: str,
    password: str,
    username: str,
    display_name: str,
    db: AsyncSession,
) -> tuple[User, str]:
    """
    Registers a new citizen user.

    Raises:
        ConflictError: if email or username is already taken.

    Returns:
        (user, access_token)
    """
    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ConflictError("An account with this email already exists")

    # Check username uniqueness
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise ConflictError("This username is already taken")

    user = User(
        id=uuid.uuid4(),
        email=email,
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
        is_guest=False,
        is_admin=False,
        is_official=False,
        is_banned=False,
        is_anonymous_default=False,
        points=0,
        level=1,
        streak_days=0,
        privacy_settings={},
        notification_preferences={
            "notify_on_status_change": True,
            "notify_on_verification": True,
            "notify_on_comment": True,
            "notify_on_resolution": True,
        },
    )
    db.add(user)
    await db.flush()  # populate user.id without committing

    token = create_access_token(str(user.id))
    logger.info("User registered", extra={"user_id": str(user.id), "username": username})
    return user, token


async def login_user(
    email: str,
    password: str,
    db: AsyncSession,
) -> tuple[User, str]:
    """
    Authenticates a user by email + password.

    Raises:
        UnauthorizedError: on bad credentials or banned account.

    Returns:
        (user, access_token)
    """
    result = await db.execute(select(User).where(User.email == email))
    user: Optional[User] = result.scalar_one_or_none()

    # Use the same error message for missing user and wrong password
    # to avoid email enumeration attacks
    if user is None or not user.password_hash:
        raise UnauthorizedError("Invalid email or password")

    if not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    if user.is_banned:
        raise UnauthorizedError("Your account has been suspended. Please contact support.")

    token = create_access_token(str(user.id))
    logger.info("User logged in", extra={"user_id": str(user.id)})
    return user, token


async def create_guest_session(db: AsyncSession) -> tuple[str, User, str]:
    """
    Creates a temporary guest user.
    Guest users can report issues without an email/password.
    Each guest gets a unique session ID and a JWT bound to their ephemeral user record.

    Returns:
        (guest_session_id, guest_user, access_token)
    """
    guest_session_id = secrets.token_urlsafe(32)

    guest_user = User(
        id=uuid.uuid4(),
        email=None,
        username=f"guest_{secrets.token_hex(6)}",
        display_name="Guest Reporter",
        password_hash=None,
        is_guest=True,
        is_admin=False,
        is_official=False,
        is_banned=False,
        is_anonymous_default=False,
        points=0,
        level=1,
        streak_days=0,
        privacy_settings={},
        notification_preferences={},
    )
    db.add(guest_user)
    await db.flush()

    token = create_access_token(str(guest_user.id))
    logger.info("Guest session created", extra={"guest_user_id": str(guest_user.id)})
    return guest_session_id, guest_user, token

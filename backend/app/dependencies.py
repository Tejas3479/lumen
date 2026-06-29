"""
Lumen FastAPI Dependencies
Shared dependencies injected via FastAPI Depends().
"""
from typing import Annotated, Optional
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.exceptions import UnauthorizedError, ForbiddenError
from app.config import settings
from jose import JWTError, jwt
import uuid


async def get_current_user_optional(
    authorization: Annotated[Optional[str], Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the current user if a valid JWT is provided.
    Returns None if no token is provided (guest/anonymous allowed).
    Raises UnauthorizedError if token is invalid.
    """
    if not authorization:
        return None
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise UnauthorizedError("Invalid authorization scheme")
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise UnauthorizedError("Invalid token payload")
        # Import here to avoid circular import
        from app.models import User
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
        if user is None:
            raise UnauthorizedError("User not found")
        return user
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")
    except ValueError:
        raise UnauthorizedError("Malformed authorization header")


async def get_current_user(
    user=Depends(get_current_user_optional),
):
    """Requires authentication. Raises 401 if not authenticated."""
    if user is None:
        raise UnauthorizedError()
    return user


async def get_admin_user(user=Depends(get_current_user)):
    """Requires admin role."""
    if not user.is_admin:
        raise ForbiddenError("Admin access required")
    return user


async def get_official_or_admin(user=Depends(get_current_user)):
    """Requires official or admin role."""
    if not (user.is_admin or user.is_official):
        raise ForbiddenError("Official or admin access required")
    return user


# Convenience type aliases
DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[object, Depends(get_current_user)]
OptionalUser = Annotated[Optional[object], Depends(get_current_user_optional)]
AdminUser = Annotated[object, Depends(get_admin_user)]
OfficialUser = Annotated[object, Depends(get_official_or_admin)]

"""
Lumen Comments Routes
POST /comments              — create comment on an issue
GET  /comments              — list comments for an issue (?issue_id=)
PATCH /comments/{id}        — edit own comment
DELETE /comments/{id}       — delete own comment (soft delete)
"""
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import (
    get_current_user,
    DB,
    CurrentUser,
)
from app.models import Comment, Issue, User
from app.schemas import CommentOut, CommentCreate, CommentUpdate
from app.exceptions import NotFoundError, ForbiddenError, ValidationError
from app.sockets.events import emit_comment_added
from app.logging_config import logger

router = APIRouter()


@router.post("", response_model=CommentOut, status_code=201)
async def create_comment(
    payload: CommentCreate,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """
    Add a comment or reply to an issue.
    parent_comment_id enables depth-1 threading.
    Official users' comments are marked is_official=True and shown prominently.
    Emits comment_added socket event.
    """
    # Verify issue exists
    issue_result = await db.execute(
        select(Issue).where(Issue.id == payload.issue_id)
    )
    issue = issue_result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("Issue", str(payload.issue_id))

    # Verify parent comment exists if threading
    if payload.parent_comment_id:
        parent_result = await db.execute(
            select(Comment).where(
                and_(
                    Comment.id == payload.parent_comment_id,
                    Comment.issue_id == payload.issue_id,
                    Comment.is_deleted == False,  # noqa: E712
                )
            )
        )
        if not parent_result.scalar_one_or_none():
            raise ValidationError(
                "Parent comment not found or belongs to a different issue"
            )

    from app.utils.sanitize import sanitize_comment
    comment = Comment(
        issue_id=payload.issue_id,
        user_id=current_user.id,
        parent_comment_id=payload.parent_comment_id,
        content=sanitize_comment(payload.content),
        is_official=current_user.is_official or current_user.is_admin,
        is_pinned=False,
        is_deleted=False,
    )
    db.add(comment)
    await db.flush()

    # Load user for socket payload
    user_result = await db.execute(select(User).where(User.id == current_user.id))
    user = user_result.scalar_one_or_none()

    comment_data = {
        "id": str(comment.id),
        "issue_id": str(comment.issue_id),
        "content": comment.content,
        "is_official": comment.is_official,
        "user_id": str(current_user.id),
        "display_name": user.display_name if user else "User",
        "is_anonymous": False,
        "created_at": comment.created_at.isoformat(),
    }

    await emit_comment_added(str(payload.issue_id), comment_data)

    logger.info(
        "Comment created",
        extra={
            "comment_id": str(comment.id),
            "issue_id": str(payload.issue_id),
            "is_official": comment.is_official,
        }
    )

    # Re-query with user relation so CommentOut.model_validate works
    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(Comment.id == comment.id)
    )
    refreshed = result.scalar_one()
    return CommentOut.model_validate(refreshed)


@router.get("", response_model=list[CommentOut])
async def list_comments(
    issue_id: uuid.UUID = Query(...),
    db: DB = None,
):
    """
    Returns all non-deleted top-level comments for an issue.
    Replies are nested under their parent in the response.
    Official comments appear first, then pinned, then by created_at ascending.
    """
    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(
            and_(
                Comment.issue_id == issue_id,
                Comment.parent_comment_id == None,  # noqa: E711
                Comment.is_deleted == False,  # noqa: E712
            )
        )
        .order_by(
            Comment.is_pinned.desc(),
            Comment.is_official.desc(),
            Comment.created_at.asc(),
        )
    )
    comments = result.scalars().all()
    return [CommentOut.model_validate(c) for c in comments]


@router.patch("/{comment_id}", response_model=CommentOut)
async def update_comment(
    comment_id: uuid.UUID,
    payload: CommentUpdate,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """
    Edit the content of a comment.
    Only the comment author or an admin may edit.
    """
    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(
            and_(
                Comment.id == comment_id,
                Comment.is_deleted == False,  # noqa: E712
            )
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise NotFoundError("Comment", str(comment_id))

    if comment.user_id != current_user.id and not current_user.is_admin:
        raise ForbiddenError("Only the comment author or admin can edit this comment")

    comment.content = payload.content.strip()
    await db.flush()
    return CommentOut.model_validate(comment)


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """
    Soft-deletes a comment (sets is_deleted=True, content replaced with placeholder).
    Replies remain but show "[comment removed]" for parent.
    """
    result = await db.execute(
        select(Comment).where(
            and_(
                Comment.id == comment_id,
                Comment.is_deleted == False,  # noqa: E712
            )
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise NotFoundError("Comment", str(comment_id))

    if comment.user_id != current_user.id and not current_user.is_admin:
        raise ForbiddenError(
            "Only the comment author or admin can delete this comment"
        )

    comment.is_deleted = True
    comment.content = "[This comment was removed]"
    await db.flush()
    return None

"""
Lumen Media Routes

POST   /media/upload          — standalone media upload (pre-upload before issue creation)
GET    /media/{media_id}      — get media metadata
DELETE /media/{media_id}      — delete media (reporter or admin)
"""
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_user_optional, get_current_user,
    DB, OptionalUser, CurrentUser,
)
from app.models import IssueMedia, Issue
from app.schemas import IssueMediaOut
from app.utils.image_processing import process_upload, validate_mime_type
from app.exceptions import NotFoundError, ForbiddenError, ValidationError
from app.config import settings
from app.logging_config import logger

router = APIRouter()


# ── POST /media/upload ────────────────────────────────────────

@router.post("/upload", response_model=IssueMediaOut, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    issue_id: str = Query(None, description="Link media to an existing issue"),
    db: DB = None,
    current_user: OptionalUser = None,
):
    """
    Standalone media upload endpoint.

    Useful for pre-uploading media before the issue form is submitted,
    reducing final submission latency on slow connections.

    If ``issue_id`` is provided, the media is linked to that issue immediately.
    If omitted, a temporary placeholder issue UUID is used; the caller is
    expected to link the returned ``media_id`` to the issue on creation.

    Validation:
      - File type detected via magic-byte MIME sniffing (not the Content-Type
        header, which clients can spoof).
      - File size enforced against ``settings.max_photo_size_mb`` /
        ``settings.max_video_size_mb``.
    """
    if not file.filename:
        raise ValidationError("No file provided")

    # ── MIME sniff before handing to processor ────────────────
    content = await file.read()
    await file.seek(0)  # reset stream for process_upload

    detected_mime = validate_mime_type(content)
    if not detected_mime:
        raise ValidationError(
            "File type not allowed. "
            "Accepted: JPEG, PNG, WebP images; "
            "MP4, MOV, WebM video; "
            "MP3, WAV, OGG, WebM audio."
        )

    # ── Resolve target issue UUID ─────────────────────────────
    PLACEHOLDER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
    target_issue_id: uuid.UUID

    if issue_id:
        try:
            target_issue_id = uuid.UUID(issue_id)
        except ValueError:
            raise ValidationError(f"Invalid issue_id: {issue_id!r}")

        result = await db.execute(select(Issue).where(Issue.id == target_issue_id))
        if not result.scalar_one_or_none():
            raise NotFoundError("Issue", issue_id)
    else:
        target_issue_id = PLACEHOLDER_ID

    # ── Process (validate size, save file, generate thumbnail) ─
    media_record = await process_upload(file, target_issue_id, db)
    if not media_record:
        raise ValidationError(
            "File processing failed. "
            "Verify the file size does not exceed the configured limit."
        )

    db.add(media_record)
    await db.flush()

    logger.info(
        "Standalone media uploaded",
        extra={
            "media_id": str(media_record.id),
            "issue_id": str(target_issue_id),
            "media_type": media_record.media_type,
            "size": media_record.file_size,
        },
    )

    return IssueMediaOut.model_validate(media_record)


# ── GET /media/{media_id} ─────────────────────────────────────

@router.get("/{media_id}", response_model=IssueMediaOut)
async def get_media(
    media_id: uuid.UUID,
    db: DB = None,
):
    """
    Return metadata for a specific media record.

    The actual file bytes are served by FastAPI StaticFiles mounted at
    ``/media/{file_path}`` — this endpoint returns only the DB record.
    """
    result = await db.execute(
        select(IssueMedia).where(IssueMedia.id == media_id)
    )
    media = result.scalar_one_or_none()
    if not media:
        raise NotFoundError("Media", str(media_id))

    return IssueMediaOut.model_validate(media)


# ── DELETE /media/{media_id} ──────────────────────────────────

@router.delete("/{media_id}", status_code=204)
async def delete_media(
    media_id: uuid.UUID,
    db: DB = None,
    current_user: CurrentUser = None,
):
    """
    Delete a media record and remove the file from disk.

    Authorization rules:
      - Admins may delete any media.
      - Non-admin users may only delete media attached to issues they reported.
      - Media uploaded with the placeholder issue UUID (standalone, not yet
        linked) is freely deletable by any authenticated user — callers should
        track their own media IDs.
    """
    result = await db.execute(
        select(IssueMedia).where(IssueMedia.id == media_id)
    )
    media = result.scalar_one_or_none()
    if not media:
        raise NotFoundError("Media", str(media_id))

    # ── Ownership check ───────────────────────────────────────
    PLACEHOLDER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
    if media.issue_id != PLACEHOLDER_ID and not current_user.is_admin:
        issue_result = await db.execute(
            select(Issue).where(Issue.id == media.issue_id)
        )
        issue = issue_result.scalar_one_or_none()
        if issue and issue.reporter_id != current_user.id:
            raise ForbiddenError(
                "Only the issue reporter or an admin can delete media"
            )

    # ── Remove file from disk ─────────────────────────────────
    base = Path(settings.media_path)

    for rel_path in (media.file_path, media.thumbnail_path):
        if not rel_path:
            continue
        full_path = base / rel_path
        if full_path.exists():
            try:
                os.remove(full_path)
            except OSError as exc:
                logger.warning(
                    "Could not remove media file",
                    extra={"path": str(full_path), "error": str(exc)},
                )

    await db.delete(media)
    await db.flush()

    logger.info(
        "Media deleted",
        extra={"media_id": str(media_id), "deleted_by": str(current_user.id)},
    )
    return None

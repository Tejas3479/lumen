"""
Lumen Offline Sync Routes

POST /offline/sync — batch-sync queued offline drafts to the server.

Each draft carries a device_idempotency_key (UUID generated on the device).
The server:
  1. Checks offline_drafts for the key; if already synced → return skipped.
  2. Creates an Issue from the draft payload.
  3. Upserts an OfflineDraft row marking synced=True and storing the issue_id.
  4. If creation fails, collects a "failed" entry without aborting the batch.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import DB, get_current_user_optional, OptionalUser
from app.models import OfflineDraft, Issue
from app.schemas import IssueCreate
from app.services.issue_service import create_issue
from app.logging_config import logger

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────


class OfflineDraftItem(BaseModel):
    device_idempotency_key: str = Field(..., min_length=1, max_length=128)
    created_locally_at: Optional[datetime] = None
    title: str = Field(..., max_length=256)
    description: str = Field(..., max_length=5000)
    latitude: float
    longitude: float
    address: Optional[str] = None
    ward: Optional[str] = None
    severity: str = "medium"
    is_anonymous: bool = False
    is_emergency: bool = False
    category_id: Optional[str] = None


class OfflineSyncRequest(BaseModel):
    drafts: List[OfflineDraftItem] = Field(default_factory=list, max_length=50)


class SyncedResult(BaseModel):
    key: str
    issue_id: str


class SkippedResult(BaseModel):
    key: str
    issue_id: str


class FailedResult(BaseModel):
    key: str
    error: str


class OfflineSyncResponse(BaseModel):
    synced: List[SyncedResult] = []
    skipped: List[SkippedResult] = []
    failed: List[FailedResult] = []


# ── Endpoint ──────────────────────────────────────────────────


@router.post("/sync", response_model=OfflineSyncResponse)
async def sync_offline_drafts(
    payload: OfflineSyncRequest,
    db: DB = None,
    current_user: OptionalUser = None,
):
    """
    Batch sync offline drafts.

    • Creates an issue for each new draft (not yet seen by server).
    • Skips drafts with keys already processed (idempotency).
    • Collects failures without aborting the entire batch.

    Returns three lists: synced, skipped, failed.
    """
    result = OfflineSyncResponse()
    user_id = current_user.id if current_user else None

    for draft in payload.drafts:
        key = draft.device_idempotency_key

        try:
            # ── Idempotency check ──────────────────────────────
            existing_result = await db.execute(
                select(OfflineDraft).where(
                    OfflineDraft.device_idempotency_key == key
                )
            )
            existing_draft = existing_result.scalar_one_or_none()

            if existing_draft and existing_draft.synced and existing_draft.synced_issue_id:
                # Already processed — return cached issue_id, no duplicate
                result.skipped.append(
                    SkippedResult(
                        key=key,
                        issue_id=str(existing_draft.synced_issue_id),
                    )
                )
                logger.info(
                    "Offline draft skipped (already synced)",
                    extra={"key": key, "issue_id": str(existing_draft.synced_issue_id)},
                )
                continue

            # ── Sanitize draft text ────────────────────────────
            from app.utils.sanitize import sanitize_issue
            draft_title, draft_description = sanitize_issue(draft.title, draft.description)

            # ── Build IssueCreate payload ──────────────────────
            issue_payload = IssueCreate(
                title=draft_title,
                description=draft_description,
                latitude=draft.latitude,
                longitude=draft.longitude,
                address=draft.address,
                ward=draft.ward,
                severity=draft.severity,
                is_anonymous=draft.is_anonymous,
                is_emergency=draft.is_emergency,
                category_id=None,
                offline_draft_id=key,
            )

            # ── Create the issue ───────────────────────────────
            issue = await create_issue(
                payload=issue_payload,
                db=db,
                reporter=current_user,
            )

            # ── Upsert the offline_drafts record ───────────────
            # The existing model uses: user_id, draft_json, synced, synced_at,
            # synced_issue_id, created_locally_at
            draft_json_payload = {
                "title": draft.title,
                "description": draft.description,
                "latitude": draft.latitude,
                "longitude": draft.longitude,
                "severity": draft.severity,
                "is_anonymous": draft.is_anonymous,
                "is_emergency": draft.is_emergency,
            }

            if existing_draft:
                # Row existed but wasn't synced — update it
                existing_draft.synced = True
                existing_draft.synced_at = datetime.now(timezone.utc)
                existing_draft.synced_issue_id = issue.id
                if user_id and not existing_draft.user_id:
                    existing_draft.user_id = user_id
            else:
                # First time seeing this key — create the tracking row
                offline_record = OfflineDraft(
                    device_idempotency_key=key,
                    user_id=user_id,
                    synced_issue_id=issue.id,
                    synced=True,
                    synced_at=datetime.now(timezone.utc),
                    created_locally_at=draft.created_locally_at or datetime.now(timezone.utc),
                    draft_json=draft_json_payload,
                )
                db.add(offline_record)

            await db.flush()

            result.synced.append(SyncedResult(key=key, issue_id=str(issue.id)))
            logger.info(
                "Offline draft synced",
                extra={"key": key, "issue_id": str(issue.id)},
            )

        except Exception as exc:
            # Log and collect — do NOT abort the entire batch
            logger.warning(
                "Offline draft sync failed",
                extra={"key": key, "error": str(exc)},
            )
            result.failed.append(FailedResult(key=key, error=str(exc)))

    return result


# ── Sync status ───────────────────────────────────────────────


@router.get("/sync/status")
async def sync_status(
    current_user: OptionalUser = None,
):
    """
    Returns current sync status.
    Simple stub for client-side polling — lets the frontend confirm
    the sync endpoint is reachable before submitting a draft batch.
    """
    return {"status": "ready", "message": "Sync endpoint is available"}

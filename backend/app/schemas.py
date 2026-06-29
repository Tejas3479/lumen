"""
Lumen Pydantic v2 Schemas
Request and response models for every API endpoint.
These are the contracts between frontend and backend.
"""
import uuid
from datetime import datetime, date
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, EmailStr, field_validator


# ── Base config ───────────────────────────────────────────────
class LumenBase(BaseModel):
    model_config = {"from_attributes": True}


# ── Category ──────────────────────────────────────────────────
class CategoryOut(LumenBase):
    id: uuid.UUID
    name: str
    display_name: str
    icon: str
    color: str
    avg_resolution_days: float
    is_active: bool


# ── User ──────────────────────────────────────────────────────
class UserPublic(LumenBase):
    id: uuid.UUID
    display_name: str
    pseudonym: Optional[str] = None
    points: int
    level: int
    is_official: bool
    department: Optional[str] = None


class UserMe(LumenBase):
    id: uuid.UUID
    email: Optional[str] = None
    username: str
    display_name: str
    is_guest: bool
    is_anonymous_default: bool
    is_admin: bool
    is_official: bool
    department: Optional[str] = None
    points: int
    level: int
    streak_days: int
    pseudonym: Optional[str] = None
    privacy_settings: Dict[str, Any] = {}
    notification_preferences: Dict[str, Any] = {}
    created_at: datetime


# ── Auth ──────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    username: str = Field(..., min_length=3, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserMe


class GuestSessionResponse(BaseModel):
    guest_session_id: str
    access_token: str
    token_type: str = "bearer"
    message: str = "Guest session created"


# ── Media ─────────────────────────────────────────────────────
class IssueMediaOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    media_type: str
    file_path: str
    file_size: int
    thumbnail_path: Optional[str] = None
    duration_seconds: Optional[int] = None
    uploaded_at: datetime


# ── Status History ────────────────────────────────────────────
class StatusHistoryOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    from_status: Optional[str] = None
    to_status: str
    changed_by: Optional[uuid.UUID] = None
    changed_by_user: Optional[UserPublic] = None
    changed_at: datetime
    note: Optional[str] = None
    is_official: bool
    is_public: bool

    model_config = {"from_attributes": True, "populate_by_name": True}


# ── Verification ──────────────────────────────────────────────
class VerificationOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    user_id: uuid.UUID
    verification_type: str
    distance_meters: Optional[float] = None
    comment: Optional[str] = None
    trust_weight: float
    created_at: datetime


class VerifyRequest(BaseModel):
    verification_type: str = Field(..., pattern="^(hard|soft)$")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    comment: Optional[str] = Field(None, max_length=500)


# ── Comment ───────────────────────────────────────────────────
class CommentOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    parent_comment_id: Optional[uuid.UUID] = None
    content: str
    is_official: bool
    is_pinned: bool
    is_deleted: bool
    user: Optional[UserPublic] = None
    replies: List["CommentOut"] = []
    created_at: datetime


CommentOut.model_rebuild()


class CommentCreate(BaseModel):
    issue_id: uuid.UUID
    content: str = Field(..., min_length=1, max_length=2000)
    parent_comment_id: Optional[uuid.UUID] = None


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


# ── Vote ──────────────────────────────────────────────────────
class VoteCreate(BaseModel):
    issue_id: uuid.UUID
    vote_type: str = Field("support", pattern="^(support|duplicate|emergency)$")
    duplicate_of: Optional[uuid.UUID] = None


class VoteOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    vote_type: str
    created_at: datetime


# ── Flag ──────────────────────────────────────────────────────
class FlagCreate(BaseModel):
    reason: str = Field(
        ..., pattern="^(spam|duplicate|inappropriate|wrong_location|resolved)$"
    )
    detail: Optional[str] = Field(None, max_length=500)


# ── Issue ─────────────────────────────────────────────────────
class IssueOut(LumenBase):
    id: uuid.UUID
    title: str
    description: str
    category_id: Optional[uuid.UUID] = None
    category: Optional[CategoryOut] = None
    ai_category: Optional[str] = None
    ai_severity: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_explanation: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_reasoning: Optional[str] = None
    ai_alternatives: Optional[dict] = None
    user_correction: bool
    severity: str
    status: str
    is_anonymous: bool
    is_emergency: bool
    reporter_id: Optional[uuid.UUID] = None
    reporter: Optional[UserPublic] = None
    assigned_to: Optional[uuid.UUID] = None
    assignee: Optional[UserPublic] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    ward: Optional[str] = None
    zone: Optional[str] = None
    vote_count: int
    verification_count: int
    view_count: int
    resolution_notes: Optional[str] = None
    media: List[IssueMediaOut] = []
    status_history: List[StatusHistoryOut] = []
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    distance_meters: Optional[float] = None


class IssueCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=256)
    description: str = Field(..., min_length=10, max_length=5000)
    category_id: Optional[uuid.UUID] = None
    severity: str = Field("medium", pattern="^(low|medium|high|critical)$")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = Field(None, max_length=512)
    ward: Optional[str] = Field(None, max_length=128)
    is_anonymous: bool = False
    is_emergency: bool = False
    offline_draft_id: Optional[str] = None  # idempotency key


class IssueUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=256)
    description: Optional[str] = Field(None, min_length=10, max_length=5000)
    category_id: Optional[uuid.UUID] = None
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")


class StatusChangeRequest(BaseModel):
    status: str = Field(
        ...,
        pattern="^(reported|verified|assigned|in_progress|resolved|disputed|closed)$",
    )
    note: Optional[str] = Field(None, max_length=1000)


class AssignRequest(BaseModel):
    assigned_to: uuid.UUID
    department: Optional[str] = Field(None, max_length=128)
    due_date: Optional[date] = None
    note: Optional[str] = Field(None, max_length=500)


class ResolutionFeedbackRequest(BaseModel):
    is_resolved: bool
    comment: Optional[str] = Field(None, max_length=1000)


class ResolutionFeedbackOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    submitted_by: Optional[uuid.UUID] = None
    is_resolved: bool
    comment: Optional[str] = None
    created_at: datetime


# ── Pagination ────────────────────────────────────────────────
class PaginatedIssues(BaseModel):
    items: List[IssueOut]
    total: int
    page: int
    per_page: int
    pages: int


# ── Verification ──────────────────────────────────────────────
class VerifyRequest(BaseModel):
    verification_type: str = Field(..., pattern="^(hard|soft)$")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    comment: Optional[str] = Field(None, max_length=500)


class VerificationOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    user_id: uuid.UUID
    verification_type: str
    distance_meters: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    comment: Optional[str] = None
    trust_weight: float
    created_at: datetime


# ── AI ────────────────────────────────────────────────────────
class AIResultOut(BaseModel):
    issue_id: uuid.UUID
    ai_category: str
    ai_severity: str
    ai_confidence: float
    ai_explanation: str
    ai_summary: str
    ai_reasoning: Optional[str] = None
    ai_alternatives: Optional[dict] = None
    is_emergency: bool


class AIFeedbackRequest(BaseModel):
    issue_id: uuid.UUID
    corrected_category: str
    corrected_severity: Optional[str] = None
    user_comment: Optional[str] = None


# ── Gamification ──────────────────────────────────────────────
class BadgeOut(LumenBase):
    id: uuid.UUID
    name: str
    display_name: str
    description: str
    icon: str
    category: str


class UserBadgeOut(LumenBase):
    badge: BadgeOut
    earned_at: datetime


class GamificationEvent(BaseModel):
    action: str
    points_awarded: int
    total_points: int
    badge_unlocked: Optional[BadgeOut] = None
    new_level: Optional[int] = None


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: uuid.UUID
    display_name: str
    pseudonym: Optional[str] = None
    points: int
    level: int
    badge_count: int
    issues_resolved_count: int


# ── Analytics ─────────────────────────────────────────────────
class DashboardStats(BaseModel):
    total_issues: int
    resolved_this_month: int
    resolution_rate: float
    avg_resolution_days: float
    issues_by_category: Dict[str, int]
    issues_by_status: Dict[str, int]
    top_wards: List[Dict[str, Any]]


class ETAResponse(BaseModel):
    issue_id: uuid.UUID
    estimated_days: float
    estimated_resolution_date: str
    confidence: str
    basis: str


# ── Predictive ────────────────────────────────────────────────
class HotspotOut(LumenBase):
    id: uuid.UUID
    category: str
    center_latitude: float
    center_longitude: float
    radius_meters: float
    issue_count: int
    predicted_next_issue_date: Optional[date] = None
    confidence: float
    generated_at: datetime
    ward: Optional[str] = None


# ── Admin ─────────────────────────────────────────────────────
class AdminBulkUpdate(BaseModel):
    issue_ids: List[uuid.UUID]
    status: str = Field(
        ...,
        pattern="^(reported|verified|assigned|in_progress|resolved|disputed|closed)$",
    )
    note: Optional[str] = None


class AdminUserModerate(BaseModel):
    is_banned: Optional[bool] = None
    is_official: Optional[bool] = None
    department: Optional[str] = None


class FlagReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(reviewed|dismissed)$")


# ── Offline Sync ──────────────────────────────────────────────
class OfflineDraftPayload(BaseModel):
    device_idempotency_key: str
    created_locally_at: datetime
    title: str
    description: str
    category_id: Optional[uuid.UUID] = None
    severity: str = "medium"
    latitude: float
    longitude: float
    address: Optional[str] = None
    ward: Optional[str] = None
    is_anonymous: bool = False
    is_emergency: bool = False


class OfflineSyncRequest(BaseModel):
    drafts: List[OfflineDraftPayload] = Field(
        ...,
        max_length=50,           # Maximum 50 drafts per sync request
        description="List of offline drafts to sync. Maximum 50 per request."
    )


class OfflineSyncResult(BaseModel):
    synced: List[Dict[str, Any]]   # [{key, issue_id}]
    skipped: List[Dict[str, Any]]  # [{key, issue_id}] — already processed
    failed: List[Dict[str, Any]]   # [{key, error}]


# ── User Settings ─────────────────────────────────────────────
class UserSettingsUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=128)
    pseudonym: Optional[str] = Field(None, max_length=64)
    is_anonymous_default: Optional[bool] = None
    privacy_settings: Optional[Dict[str, Any]] = None
    notification_preferences: Optional[Dict[str, Any]] = None


# ── Admin Schemas ─────────────────────────────────────────────

class AdminBulkUpdate(BaseModel):
    """Bulk status update for multiple issues."""
    issue_ids: List[uuid.UUID]
    status: str
    note: Optional[str] = Field(None, max_length=500)


class AdminUserModerate(BaseModel):
    """Moderate a user: ban/unban, set official status, assign dept."""
    is_banned: Optional[bool] = None
    is_official: Optional[bool] = None
    department: Optional[str] = Field(None, max_length=128)


class FlagReviewRequest(BaseModel):
    """Review a moderation flag."""
    status: str  # 'reviewed' | 'dismissed'
    note: Optional[str] = Field(None, max_length=500)


# ── Analytics Schemas ─────────────────────────────────────────

class DashboardStats(BaseModel):
    """Aggregate impact dashboard statistics."""
    total_issues: int
    resolved_this_month: int
    resolution_rate: float
    avg_resolution_days: float
    issues_by_category: Dict[str, int]
    issues_by_status: Dict[str, int]
    top_wards: List[Dict[str, Any]]


class ETAResponse(BaseModel):
    """Estimated resolution time for a specific issue."""
    issue_id: uuid.UUID
    estimated_days: float
    estimated_resolution_date: str
    confidence: str  # 'high' | 'medium' | 'low'
    basis: str


class HotspotOut(LumenBase):
    """A predicted geographic issue hotspot."""
    id: uuid.UUID
    category: str
    center_latitude: float
    center_longitude: float
    radius_meters: float
    issue_count: int
    predicted_next_issue_date: Optional[date] = None
    confidence: float
    ward: Optional[str] = None


# ── Gamification Schemas ──────────────────────────────────────

class LeaderboardEntry(LumenBase):
    """A single entry in the gamification leaderboard."""
    rank: int
    user_id: uuid.UUID
    display_name: str
    pseudonym: Optional[str] = None
    points: int
    level: int
    badge_count: int
    issues_resolved_count: int
    streak_days: int


class TriageReportOut(LumenBase):
    id: uuid.UUID
    issue_id: uuid.UUID
    reasoning_steps: list
    recommended_department: Optional[str]
    recommended_priority: int
    recommended_action: str
    recommendation_summary: str
    auto_applied: bool
    auto_applied_at: Optional[datetime]
    agent_model: str
    confidence: float
    generated_at: datetime


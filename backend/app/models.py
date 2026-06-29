"""
Lumen ORM Models
All 17 SQLAlchemy models for the complete civic issue lifecycle.
Inherits from app.database.Base.
Uses UUID primary keys throughout for security (no enumerable integer IDs).
"""
import uuid
from datetime import datetime, date, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Text, Boolean, Float, Integer, DateTime, Date,
    ForeignKey, UniqueConstraint, Index,
    JSON, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────────
# 1. categories
# ─────────────────────────────────────────────
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[str] = mapped_column(String(64), nullable=False, default="alert-circle")
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#718096")
    avg_resolution_days: Mapped[float] = mapped_column(Float, nullable=False, default=7.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="category")


# ─────────────────────────────────────────────
# 2. users
# ─────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    email: Mapped[Optional[str]] = mapped_column(String(256), unique=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_anonymous_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    privacy_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notification_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fcm_token: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    pseudonym: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # Relationships
    reported_issues: Mapped[List["Issue"]] = relationship(
        "Issue", foreign_keys="Issue.reporter_id", back_populates="reporter"
    )
    assigned_issues: Mapped[List["Issue"]] = relationship(
        "Issue", foreign_keys="Issue.assigned_to", back_populates="assignee"
    )
    verifications: Mapped[List["Verification"]] = relationship(
        "Verification", back_populates="user"
    )
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="user")
    votes: Mapped[List["Vote"]] = relationship("Vote", back_populates="user")
    badges: Mapped[List["UserBadge"]] = relationship("UserBadge", back_populates="user", cascade="all, delete-orphan")
    points_log: Mapped[List["LeaderboardPoints"]] = relationship(
        "LeaderboardPoints", back_populates="user", cascade="all, delete-orphan"
    )
    resolution_feedbacks: Mapped[List["ResolutionFeedback"]] = relationship(
        "ResolutionFeedback", back_populates="submitter"
    )


# ─────────────────────────────────────────────
# 3. issues
# ─────────────────────────────────────────────
class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    # AI fields
    ai_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ai_severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_alternatives: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    user_correction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Core fields
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="reported")
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Reporter — nullable for anonymous
    reporter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    guest_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Assignment
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Location
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ward: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    zone: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Counts (denormalized for query performance)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verification_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Resolution
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # Offline sync idempotency
    offline_draft_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="issues")
    reporter: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[reporter_id], back_populates="reported_issues"
    )
    assignee: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_to], back_populates="assigned_issues"
    )
    media: Mapped[List["IssueMedia"]] = relationship(
        "IssueMedia", back_populates="issue", cascade="all, delete-orphan"
    )
    status_history: Mapped[List["StatusHistory"]] = relationship(
        "StatusHistory", back_populates="issue", cascade="all, delete-orphan",
        order_by="StatusHistory.changed_at",
    )
    verifications: Mapped[List["Verification"]] = relationship(
        "Verification", back_populates="issue", cascade="all, delete-orphan"
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment", back_populates="issue", cascade="all, delete-orphan"
    )
    votes: Mapped[List["Vote"]] = relationship(
        "Vote", back_populates="issue", cascade="all, delete-orphan",
        foreign_keys="[Vote.issue_id]"
    )
    flags: Mapped[List["Flag"]] = relationship(
        "Flag", back_populates="issue", cascade="all, delete-orphan"
    )
    audit_log: Mapped[List["IssueAuditLog"]] = relationship(
        "IssueAuditLog", back_populates="issue", cascade="all, delete-orphan"
    )
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment", back_populates="issue", cascade="all, delete-orphan"
    )
    resolution_feedbacks: Mapped[List["ResolutionFeedback"]] = relationship(
        "ResolutionFeedback", back_populates="issue", cascade="all, delete-orphan"
    )
    points_log: Mapped[List["LeaderboardPoints"]] = relationship(
        "LeaderboardPoints", back_populates="issue"
    )

    __table_args__ = (
        Index("ix_issues_status", "status"),
        Index("ix_issues_created_at", "created_at"),
        Index("ix_issues_lat_lng", "latitude", "longitude"),
        Index("ix_issues_ward", "ward"),
        Index("ix_issues_is_emergency", "is_emergency"),
        Index("ix_issues_reporter_id", "reporter_id"),
        Index("ix_issues_category_id", "category_id"),
        Index("ix_issues_offline_draft_id", "offline_draft_id"),
    )


# ─────────────────────────────────────────────
# 4. issue_media
# ─────────────────────────────────────────────
class IssueMedia(Base):
    __tablename__ = "issue_media"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)  # photo/video/voice
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="media")

    __table_args__ = (
        Index("ix_issue_media_issue_id", "issue_id"),
    )


# ─────────────────────────────────────────────
# 5. status_history
# ─────────────────────────────────────────────
class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    issue: Mapped["Issue"] = relationship("Issue", back_populates="status_history")
    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[changed_by])

    __table_args__ = (
        Index("ix_status_history_issue_id", "issue_id"),
        Index("ix_status_history_changed_at", "changed_at"),
    )


# ─────────────────────────────────────────────
# 6. verifications
# ─────────────────────────────────────────────
class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verification_type: Mapped[str] = mapped_column(String(16), nullable=False)  # hard/soft
    distance_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trust_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="verifications")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="verifications")

    __table_args__ = (
        Index(
            "ix_verif_issue_user_unique",
            "issue_id", "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index("ix_verifications_issue_id", "issue_id"),
    )


# ─────────────────────────────────────────────
# 7. comments
# ─────────────────────────────────────────────
class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    parent_comment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="comments")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="comments")
    replies: Mapped[List["Comment"]] = relationship(
        "Comment", back_populates="parent", cascade="all"
    )
    parent: Mapped[Optional["Comment"]] = relationship(
        "Comment", back_populates="replies", remote_side="Comment.id"
    )

    __table_args__ = (
        Index("ix_comments_issue_id", "issue_id"),
    )


# ─────────────────────────────────────────────
# 8. votes
# ─────────────────────────────────────────────
class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    guest_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vote_type: Mapped[str] = mapped_column(String(16), nullable=False, default="support")
    duplicate_of: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship(
        "Issue", foreign_keys=[issue_id], back_populates="votes"
    )
    user: Mapped[Optional["User"]] = relationship("User", back_populates="votes")

    __table_args__ = (
        UniqueConstraint("issue_id", "user_id", name="uq_vote_issue_user"),
        Index("ix_votes_issue_id", "issue_id"),
    )


# ─────────────────────────────────────────────
# 9. flags
# ─────────────────────────────────────────────
class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    flagged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="flags")
    reporter: Mapped[Optional["User"]] = relationship("User", foreign_keys=[flagged_by])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])

    __table_args__ = (
        Index("ix_flags_issue_id", "issue_id"),
        Index("ix_flags_status", "status"),
    )


# ─────────────────────────────────────────────
# 10. badges
# ─────────────────────────────────────────────
class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    points_required: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    condition_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user_badges: Mapped[List["UserBadge"]] = relationship(
        "UserBadge", back_populates="badge"
    )


# ─────────────────────────────────────────────
# 11. user_badges
# ─────────────────────────────────────────────
class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    badge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("badges.id"), nullable=False
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="badges")
    badge: Mapped["Badge"] = relationship("Badge", back_populates="user_badges")

    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )


# ─────────────────────────────────────────────
# 12. leaderboard_points
# ─────────────────────────────────────────────
class LeaderboardPoints(Base):
    __tablename__ = "leaderboard_points"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="points_log")
    issue: Mapped[Optional["Issue"]] = relationship("Issue", back_populates="points_log")

    __table_args__ = (
        Index("ix_leaderboard_user_id", "user_id"),
        Index("ix_leaderboard_created_at", "created_at"),
    )


# ─────────────────────────────────────────────
# 13. predictive_hotspots
# ─────────────────────────────────────────────
class PredictiveHotspot(Base):
    __tablename__ = "predictive_hotspots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    center_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    center_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_meters: Mapped[float] = mapped_column(Float, nullable=False)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_next_issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    ward: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_hotspots_category", "category"),
        Index("ix_hotspots_generated_at", "generated_at"),
    )


# ─────────────────────────────────────────────
# 14. resolution_feedback
# ─────────────────────────────────────────────
class ResolutionFeedback(Base):
    __tablename__ = "resolution_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    submitted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dispute_triggers_reopen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="resolution_feedbacks")
    submitter: Mapped[Optional["User"]] = relationship(
        "User", back_populates="resolution_feedbacks"
    )

    __table_args__ = (
        Index("ix_resolution_feedback_issue_id", "issue_id"),
    )


# ─────────────────────────────────────────────
# 15. offline_drafts
# ─────────────────────────────────────────────
class OfflineDraft(Base):
    __tablename__ = "offline_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    device_idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    guest_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    draft_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    media_paths: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    synced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sync_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_locally_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_issue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_offline_drafts_key", "device_idempotency_key"),
        Index("ix_offline_drafts_synced", "synced"),
    )


# ─────────────────────────────────────────────
# 16. issue_audit_log
# ─────────────────────────────────────────────
class IssueAuditLog(Base):
    __tablename__ = "issue_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="audit_log")
    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_audit_log_issue_id", "issue_id"),
        Index("ix_audit_log_created_at", "created_at"),
    )


# ─────────────────────────────────────────────
# 17. assignments
# ─────────────────────────────────────────────
class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="assignments")
    assignee: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to])
    assigner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_by])

    __table_args__ = (
        Index("ix_assignments_issue_id", "issue_id"),
        Index("ix_assignments_assigned_to", "assigned_to"),
    )


class TriageReport(Base):
    __tablename__ = "triage_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One triage report per issue
    )
    # Agent reasoning trace
    reasoning_steps: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    # Agent recommendation
    recommended_department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    recommended_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # Priority 1 = highest, 10 = lowest
    recommended_action: Mapped[str] = mapped_column(String(64), nullable=False, default="review")
    # Actions: auto_assign | escalate_emergency | flag_duplicate | request_verification | review
    recommendation_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Was the recommendation auto-applied?
    auto_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Agent metadata
    agent_model: Mapped[str] = mapped_column(String(64), nullable=False, default="gemini-3.5-flash")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    issue: Mapped["Issue"] = relationship("Issue", backref="triage_report")

    __table_args__ = (
        Index("ix_triage_reports_issue_id", "issue_id"),
        Index("ix_triage_reports_recommended_priority", "recommended_priority"),
    )


class WardReport(Base):
    __tablename__ = "ward_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    ward: Mapped[str] = mapped_column(String(128), nullable=False)
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Raw stats (JSON for flexibility)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # AI-generated narrative
    narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    headline: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    key_achievements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    key_concerns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    agent_model: Mapped[str] = mapped_column(String(64), nullable=False, default="gemini-3.5-flash")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        Index("ix_ward_reports_ward", "ward"),
        Index("ix_ward_reports_week_start", "week_start"),
    )



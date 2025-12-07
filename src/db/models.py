"""
SQLAlchemy database models.

Defines all database tables for the Lexia API.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: JSONB,
    }


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# =============================================================================
# API Key Management
# =============================================================================


class APIKey(Base, TimestampMixin):
    """API Key for authentication."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Permissions and limits
    permissions: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    rate_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=60,
    )

    # Status
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="api_key",
        lazy="dynamic",
    )
    transcriptions: Mapped[list["Transcription"]] = relationship(
        "Transcription",
        back_populates="api_key",
        lazy="dynamic",
    )

    __table_args__ = (
        Index("ix_api_keys_user_org", "user_id", "organization_id"),
    )


# =============================================================================
# Jobs (Async Processing)
# =============================================================================


class Job(Base, TimestampMixin):
    """Async job for long-running tasks."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="normal",
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Input/Output
    params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    result_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Progress
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    progress_message: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Error handling
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    retries: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    # Webhook
    webhook_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    webhook_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Ownership
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Extra data (note: "metadata" is reserved by SQLAlchemy)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Celery task ID
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )

    # Relationships
    api_key: Mapped[APIKey | None] = relationship(
        "APIKey",
        back_populates="jobs",
    )

    __table_args__ = (
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_user_status", "user_id", "status"),
    )


# =============================================================================
# Transcriptions
# =============================================================================


class Transcription(Base, TimestampMixin):
    """Stored transcription result."""

    __tablename__ = "transcriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="processing",
        index=True,
    )

    # Audio info
    audio_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    audio_storage_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    audio_duration: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    audio_format: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Transcription config
    language_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    language_detected: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    language_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    speaker_diarization: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    word_timestamps: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Results
    text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    segments: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    words: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    speakers: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    utterances: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Diarization results
    diarization_segments: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    diarization_stats: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Error
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Timing
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processing_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Ownership
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Extra data (note: "metadata" is reserved by SQLAlchemy)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    api_key: Mapped[APIKey | None] = relationship(
        "APIKey",
        back_populates="transcriptions",
    )

    __table_args__ = (
        Index("ix_transcriptions_user_status", "user_id", "status"),
    )


# =============================================================================
# Usage Tracking
# =============================================================================


class UsageRecord(Base):
    """Track API usage for billing and monitoring."""

    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Endpoint info
    endpoint: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    # Usage metrics
    tokens_input: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    tokens_output: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    audio_seconds: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Request info
    status_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_usage_api_key_time", "api_key_id", "timestamp"),
        Index("ix_usage_user_time", "user_id", "timestamp"),
    )

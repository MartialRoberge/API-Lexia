"""
Pydantic models for async job management.

Jobs are used for long-running tasks like audio transcription.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.models.common import StrictBaseModel


class JobType(str, Enum):
    """Types of async jobs."""

    TRANSCRIPTION = "transcription"
    DIARIZATION = "diarization"
    TRANSCRIPTION_WITH_DIARIZATION = "transcription_with_diarization"


class JobStatus(str, Enum):
    """Status of an async job."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(str, Enum):
    """Job priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class JobProgress(StrictBaseModel):
    """Progress information for a running job."""

    percentage: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Completion percentage",
    )
    stage: str | None = Field(
        default=None,
        description="Current processing stage",
    )
    message: str | None = Field(
        default=None,
        description="Progress message",
    )
    items_processed: int | None = Field(
        default=None,
        description="Number of items processed",
    )
    items_total: int | None = Field(
        default=None,
        description="Total items to process",
    )


class JobError(StrictBaseModel):
    """Error information for a failed job."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional error details",
    )
    retryable: bool = Field(
        default=False,
        description="Whether the job can be retried",
    )


class JobCreate(StrictBaseModel):
    """Request to create a new async job."""

    type: JobType = Field(..., description="Type of job to create")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Job parameters",
    )
    priority: JobPriority = Field(
        default=JobPriority.NORMAL,
        description="Job priority",
    )
    webhook_url: str | None = Field(
        default=None,
        description="Webhook URL for completion notification",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Custom metadata",
    )


class JobResponse(StrictBaseModel):
    """Response containing job information."""

    id: str = Field(..., description="Unique job ID")
    type: JobType = Field(..., description="Job type")
    status: JobStatus = Field(..., description="Current status")

    # Timing
    created_at: datetime = Field(..., description="Creation timestamp")
    started_at: datetime | None = Field(
        default=None,
        description="Processing start time",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Completion time",
    )

    # Progress
    progress: JobProgress | None = Field(
        default=None,
        description="Progress information",
    )

    # Result
    result_url: str | None = Field(
        default=None,
        description="URL to fetch results",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Job result (for small results)",
    )

    # Error
    error: JobError | None = Field(
        default=None,
        description="Error details if failed",
    )

    # Metadata
    priority: JobPriority = Field(default=JobPriority.NORMAL)
    metadata: dict[str, Any] | None = Field(default=None)
    webhook_url: str | None = Field(default=None)

    # User info
    user_id: str | None = Field(
        default=None,
        description="Owner user ID",
    )
    organization_id: str | None = Field(
        default=None,
        description="Owner organization ID",
    )


class JobListResponse(StrictBaseModel):
    """Response for listing jobs."""

    jobs: list[JobResponse] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total number of jobs")
    has_more: bool = Field(..., description="Whether more jobs exist")


class JobCancelRequest(StrictBaseModel):
    """Request to cancel a job."""

    reason: str | None = Field(
        default=None,
        max_length=256,
        description="Cancellation reason",
    )


class JobRetryRequest(StrictBaseModel):
    """Request to retry a failed job."""

    priority: JobPriority | None = Field(
        default=None,
        description="New priority (optional)",
    )


class WebhookPayload(StrictBaseModel):
    """Payload sent to webhook on job completion."""

    event: str = Field(..., description="Event type (e.g., 'job.completed')")
    job_id: str = Field(..., description="Job ID")
    job_type: JobType = Field(..., description="Job type")
    status: JobStatus = Field(..., description="Final status")
    completed_at: datetime = Field(..., description="Completion timestamp")
    result_url: str | None = Field(default=None)
    error: JobError | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)

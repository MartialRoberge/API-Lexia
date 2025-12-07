"""
Jobs API router.

Provides job management endpoints for async operations.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import CurrentUser
from src.core.exceptions import JobNotFoundError
from src.db.repositories.job import JobRepository
from src.db.session import get_db
from src.models.jobs import (
    JobError,
    JobProgress,
    JobResponse,
    JobStatus,
    JobType,
)

router = APIRouter(prefix="/v1/jobs", tags=["Jobs"])


def map_job_status(status: str) -> JobStatus:
    """Map database status to JobStatus enum."""
    status_map = {
        "pending": JobStatus.PENDING,
        "queued": JobStatus.QUEUED,
        "processing": JobStatus.PROCESSING,
        "completed": JobStatus.COMPLETED,
        "failed": JobStatus.FAILED,
        "cancelled": JobStatus.CANCELLED,
    }
    return status_map.get(status, JobStatus.PENDING)


def map_job_type(job_type: str) -> JobType:
    """Map database type to JobType enum."""
    type_map = {
        "transcription": JobType.TRANSCRIPTION,
        "diarization": JobType.DIARIZATION,
        "transcription_with_diarization": JobType.TRANSCRIPTION_WITH_DIARIZATION,
    }
    return type_map.get(job_type, JobType.TRANSCRIPTION)


@router.get(
    "",
    response_model=list[JobResponse],
    summary="List jobs",
    description="List jobs for the authenticated user.",
)
async def list_jobs(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: JobStatus | None = Query(None, description="Filter by status"),
    job_type: JobType | None = Query(None, description="Filter by type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[JobResponse]:
    """
    List jobs.

    Returns paginated list of jobs for the authenticated user.
    """
    job_repo = JobRepository(db)

    jobs = await job_repo.get_by_user(
        user_id=user.user_id,
        status=status.value if status else None,
        job_type=job_type.value if job_type else None,
        limit=limit,
        offset=offset,
    )

    return [
        JobResponse(
            id=str(job.id),
            type=map_job_type(job.type),
            status=map_job_status(job.status),
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            progress=JobProgress(
                percentage=job.progress_percent,
                message=job.progress_message,
            ) if job.progress_percent > 0 else None,
            result_url=job.result_url,
            result=job.result,
            error=JobError(
                code=job.error_code or "ERROR",
                message=job.error_message or "Unknown error",
            ) if job.error_message else None,
            metadata=job.metadata,
            webhook_url=job.webhook_url,
            user_id=job.user_id,
        )
        for job in jobs
    ]


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job",
    description="Get details of a specific job.",
)
async def get_job(
    job_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    """
    Get job by ID.

    Returns full job details including progress and results.
    """
    job_repo = JobRepository(db)

    job = await job_repo.get_by_id(uuid.UUID(job_id))
    if job is None:
        raise JobNotFoundError(job_id)

    # Check ownership
    if job.user_id != user.user_id:
        raise JobNotFoundError(job_id)

    return JobResponse(
        id=str(job.id),
        type=map_job_type(job.type),
        status=map_job_status(job.status),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        progress=JobProgress(
            percentage=job.progress_percent,
            message=job.progress_message,
        ) if job.progress_percent > 0 else None,
        result_url=job.result_url,
        result=job.result,
        error=JobError(
            code=job.error_code or "ERROR",
            message=job.error_message or "Unknown error",
        ) if job.error_message else None,
        metadata=job.metadata,
        webhook_url=job.webhook_url,
        user_id=job.user_id,
    )


@router.delete(
    "/{job_id}",
    status_code=204,
    summary="Cancel job",
    description="Cancel a pending or queued job.",
)
async def cancel_job(
    job_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """
    Cancel a job.

    Only pending or queued jobs can be cancelled.
    """
    job_repo = JobRepository(db)

    job = await job_repo.get_by_id(uuid.UUID(job_id))
    if job is None:
        raise JobNotFoundError(job_id)

    if job.user_id != user.user_id:
        raise JobNotFoundError(job_id)

    if job.status not in ("pending", "queued"):
        from src.core.exceptions import ValidationError
        raise ValidationError(
            message="Only pending or queued jobs can be cancelled",
            details={"current_status": job.status},
        )

    # Cancel Celery task if exists
    if job.celery_task_id:
        from src.workers.celery_app import app
        app.control.revoke(job.celery_task_id, terminate=True)

    await job_repo.update_status(job.id, "cancelled")
    await db.commit()

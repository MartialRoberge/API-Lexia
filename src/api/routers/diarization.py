"""
Diarization API router.

Provides speaker diarization endpoints.
"""

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import CurrentUser
from src.core.config import Settings, get_settings
from src.core.exceptions import FileTooLargeError, InvalidAudioFormatError, JobNotFoundError
from src.core.rate_limit import RateLimitedUser
from src.db.repositories.job import JobRepository
from src.db.session import get_db
from src.models.stt import (
    DiarizationResponse,
    DiarizationStats,
    TranscriptionStatus,
)
from src.services.diarization.factory import get_diarization_backend
from src.services.storage.factory import get_storage_backend
from src.workers.tasks.diarization import process_diarization

router = APIRouter(prefix="/v1", tags=["Diarization"])


SUPPORTED_FORMATS = ["wav", "mp3", "m4a", "flac", "ogg", "webm"]


def validate_audio_format(filename: str) -> str:
    """Validate and return audio format from filename."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_FORMATS:
        raise InvalidAudioFormatError(ext, SUPPORTED_FORMATS)
    return ext


@router.post(
    "/diarization",
    response_model=DiarizationResponse,
    status_code=202,
    summary="Create diarization job",
    description="Upload audio and create an async speaker diarization job.",
)
async def create_diarization(
    user: RateLimitedUser,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
    audio: UploadFile | None = File(None),
    audio_url: str | None = Form(None),
    num_speakers: int | None = Form(None, ge=1, le=20),
    min_speakers: int | None = Form(None, ge=1),
    max_speakers: int | None = Form(None, le=20),
    webhook_url: str | None = Form(None),
) -> DiarizationResponse:
    """
    Create a speaker diarization job.

    Returns a job ID for polling the result.
    """
    storage = get_storage_backend(settings)
    job_repo = JobRepository(db)

    audio_storage_key = None

    if audio is not None:
        audio_format = validate_audio_format(audio.filename or "audio.wav")

        audio.file.seek(0, 2)
        size = audio.file.tell()
        audio.file.seek(0)

        max_size = settings.stt_max_file_size_mb * 1024 * 1024
        if size > max_size:
            raise FileTooLargeError(size / (1024 * 1024), settings.stt_max_file_size_mb)

        content = await audio.read()
        audio_storage_key = storage.generate_key(
            audio.filename or f"audio.{audio_format}",
            prefix="diarization",
        )
        await storage.upload(audio_storage_key, content, f"audio/{audio_format}")

    elif audio_url is None:
        raise InvalidAudioFormatError("none", SUPPORTED_FORMATS)

    # Create job
    job = await job_repo.create(
        job_type="diarization",
        params={
            "num_speakers": num_speakers,
            "min_speakers": min_speakers,
            "max_speakers": max_speakers,
        },
        user_id=user.user_id,
        api_key_id=uuid.UUID(user.api_key_id),
        webhook_url=webhook_url,
    )

    await db.commit()

    # Queue async processing
    if audio_storage_key:
        task = process_diarization.delay(
            str(job.id),
            audio_storage_key,
            num_speakers,
            min_speakers,
            max_speakers,
        )
        await job_repo.set_celery_task_id(job.id, task.id)
        await db.commit()

    return DiarizationResponse(
        id=str(job.id),
        status=TranscriptionStatus.QUEUED,
        created_at=job.created_at,
    )


@router.get(
    "/diarization/{job_id}",
    response_model=DiarizationResponse,
    summary="Get diarization result",
    description="Get the status and result of a diarization job.",
)
async def get_diarization(
    job_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DiarizationResponse:
    """
    Get diarization result by job ID.
    """
    job_repo = JobRepository(db)

    job = await job_repo.get_by_id(uuid.UUID(job_id))
    if job is None or job.type != "diarization":
        raise JobNotFoundError(job_id)

    if job.user_id != user.user_id:
        raise JobNotFoundError(job_id)

    status_map = {
        "pending": TranscriptionStatus.QUEUED,
        "queued": TranscriptionStatus.QUEUED,
        "processing": TranscriptionStatus.PROCESSING,
        "completed": TranscriptionStatus.COMPLETED,
        "failed": TranscriptionStatus.FAILED,
    }

    response = DiarizationResponse(
        id=str(job.id),
        status=status_map.get(job.status, TranscriptionStatus.QUEUED),
        created_at=job.created_at,
        completed_at=job.completed_at,
    )

    if job.result:
        from src.models.stt import Speaker, SpeakerSegment

        response.speakers = [
            Speaker(**s) for s in job.result.get("speakers", [])
        ]
        response.segments = [
            SpeakerSegment(**s) for s in job.result.get("segments", [])
        ]
        if job.result.get("stats"):
            response.stats = DiarizationStats(**job.result["stats"])
        response.rttm = job.result.get("rttm")

    if job.error_message:
        response.error = job.error_message

    return response


@router.post(
    "/diarization/sync",
    response_model=DiarizationResponse,
    summary="Sync diarization",
    description="Diarize audio synchronously (for short files only).",
)
async def sync_diarization(
    user: RateLimitedUser,
    settings: Annotated[Settings, Depends(get_settings)],
    audio: UploadFile = File(...),
    num_speakers: int | None = Form(None, ge=1, le=20),
    min_speakers: int | None = Form(None, ge=1),
    max_speakers: int | None = Form(None, le=20),
) -> DiarizationResponse:
    """
    Synchronous diarization for short audio.
    """
    audio_format = validate_audio_format(audio.filename or "audio.wav")

    audio.file.seek(0, 2)
    size = audio.file.tell()
    audio.file.seek(0)

    if size > 50 * 1024 * 1024:
        raise FileTooLargeError(size / (1024 * 1024), 50)

    content = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        backend = get_diarization_backend(settings)
        result = await backend.diarize(
            temp_path,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )

        return DiarizationResponse(
            id=str(uuid.uuid4()),
            status=TranscriptionStatus.COMPLETED,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            speakers=result.speakers,
            segments=result.segments,
            overlaps=result.overlaps,
            stats=result.stats,
            rttm=result.rttm,
        )

    finally:
        temp_path.unlink(missing_ok=True)

"""
Speech-to-Text API router.

Provides transcription endpoints for audio files.
"""

import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import CurrentUser
from src.core.config import Settings, get_settings
from src.core.exceptions import (
    FileTooLargeError,
    InvalidAudioFormatError,
    TranscriptionNotFoundError,
)
from src.core.rate_limit import RateLimitedUser
from src.db.repositories.job import JobRepository
from src.db.repositories.transcription import TranscriptionRepository
from src.db.session import get_db
from src.models.stt import (
    LanguageCode,
    TranscriptionJob,
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptionStatus,
)
from src.services.stt.factory import get_stt_backend
from src.services.storage.factory import get_storage_backend
from src.workers.tasks.transcription import process_transcription

router = APIRouter(prefix="/v1", tags=["Speech-to-Text"])


SUPPORTED_FORMATS = ["wav", "mp3", "m4a", "flac", "ogg", "webm"]


def validate_audio_format(filename: str) -> str:
    """Validate and return audio format from filename."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_FORMATS:
        raise InvalidAudioFormatError(ext, SUPPORTED_FORMATS)
    return ext


@router.post(
    "/transcriptions",
    response_model=TranscriptionJob,
    status_code=202,
    summary="Create transcription job",
    description="Upload audio and create an async transcription job.",
)
async def create_transcription(
    user: RateLimitedUser,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
    audio: UploadFile | None = File(None, description="Audio file to transcribe"),
    audio_url: str | None = Form(None, description="URL to audio file"),
    language_code: LanguageCode = Form(LanguageCode.FR),
    speaker_diarization: bool = Form(False),
    word_timestamps: bool = Form(True),
    webhook_url: str | None = Form(None),
) -> TranscriptionJob:
    """
    Create a new transcription job.

    Upload an audio file or provide a URL for transcription.
    Returns a job ID for polling the result.
    """
    storage = get_storage_backend(settings)
    job_repo = JobRepository(db)
    trans_repo = TranscriptionRepository(db)

    # Determine audio source
    audio_storage_key = None
    source_url = audio_url

    if audio is not None:
        # Validate format
        audio_format = validate_audio_format(audio.filename or "audio.wav")

        # Check file size
        audio.file.seek(0, 2)
        size = audio.file.tell()
        audio.file.seek(0)

        max_size = settings.stt_max_file_size_mb * 1024 * 1024
        if size > max_size:
            raise FileTooLargeError(
                size / (1024 * 1024),
                settings.stt_max_file_size_mb,
            )

        # Upload to storage
        content = await audio.read()
        audio_storage_key = storage.generate_key(
            audio.filename or f"audio.{audio_format}",
            prefix="transcriptions",
        )
        await storage.upload(audio_storage_key, content, f"audio/{audio_format}")

    elif audio_url is not None:
        source_url = audio_url
    else:
        raise InvalidAudioFormatError("none", SUPPORTED_FORMATS)

    # Create job
    job = await job_repo.create(
        job_type="transcription",
        params={
            "language_code": language_code.value,
            "speaker_diarization": speaker_diarization,
            "word_timestamps": word_timestamps,
        },
        user_id=user.user_id,
        api_key_id=uuid.UUID(user.api_key_id),
        webhook_url=webhook_url,
    )

    # Create transcription record
    transcription = await trans_repo.create(
        job_id=job.id,
        audio_url=source_url,
        audio_storage_key=audio_storage_key,
        language_code=language_code.value if language_code != LanguageCode.AUTO else None,
        speaker_diarization=speaker_diarization,
        word_timestamps=word_timestamps,
        user_id=user.user_id,
        api_key_id=uuid.UUID(user.api_key_id),
    )

    await db.commit()

    # Queue async processing
    if audio_storage_key:
        task = process_transcription.delay(
            str(job.id),
            audio_storage_key,
            language_code.value if language_code != LanguageCode.AUTO else None,
            speaker_diarization,
            word_timestamps,
        )
        await job_repo.set_celery_task_id(job.id, task.id)
        await db.commit()

    return TranscriptionJob(
        id=str(transcription.id),
        status=TranscriptionStatus.QUEUED,
        created_at=job.created_at,
    )


@router.get(
    "/transcriptions/{transcription_id}",
    response_model=TranscriptionResponse,
    summary="Get transcription",
    description="Get the status and result of a transcription.",
)
async def get_transcription(
    transcription_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TranscriptionResponse:
    """
    Get transcription by ID.

    Returns the transcription status and result if complete.
    """
    trans_repo = TranscriptionRepository(db)

    transcription = await trans_repo.get_by_id(uuid.UUID(transcription_id))
    if transcription is None:
        raise TranscriptionNotFoundError(transcription_id)

    # Check ownership
    if transcription.user_id != user.user_id:
        raise TranscriptionNotFoundError(transcription_id)

    # Map status
    status_map = {
        "processing": TranscriptionStatus.PROCESSING,
        "completed": TranscriptionStatus.COMPLETED,
        "failed": TranscriptionStatus.FAILED,
    }

    return TranscriptionResponse(
        id=str(transcription.id),
        status=status_map.get(transcription.status, TranscriptionStatus.QUEUED),
        created_at=transcription.created_at,
        completed_at=transcription.completed_at,
        audio_url=transcription.audio_url,
        audio_duration=transcription.audio_duration,
        text=transcription.text,
        segments=transcription.segments,
        words=transcription.words,
        language_code=transcription.language_detected or transcription.language_code,
        language_confidence=transcription.language_confidence,
        speakers=transcription.speakers,
        utterances=transcription.utterances,
        error=transcription.error,
        metadata=transcription.metadata,
    )


@router.post(
    "/transcriptions/sync",
    response_model=TranscriptionResponse,
    summary="Sync transcription",
    description="Transcribe audio synchronously (for short files only).",
)
async def sync_transcription(
    user: RateLimitedUser,
    settings: Annotated[Settings, Depends(get_settings)],
    audio: UploadFile = File(..., description="Audio file to transcribe"),
    language_code: LanguageCode = Form(LanguageCode.FR),
    word_timestamps: bool = Form(True),
) -> TranscriptionResponse:
    """
    Synchronous transcription.

    For short audio files (<5 minutes). Returns result immediately.
    For longer files, use the async endpoint.
    """
    # Validate format
    audio_format = validate_audio_format(audio.filename or "audio.wav")

    # Check file size (limit for sync: 50MB)
    audio.file.seek(0, 2)
    size = audio.file.tell()
    audio.file.seek(0)

    if size > 50 * 1024 * 1024:
        raise FileTooLargeError(
            size / (1024 * 1024),
            50,
        )

    # Save to temp file
    content = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        # Transcribe
        stt_backend = get_stt_backend(settings)
        result = await stt_backend.transcribe(
            temp_path,
            language=language_code.value if language_code != LanguageCode.AUTO else None,
            word_timestamps=word_timestamps,
        )

        # Build response
        segments = [
            {
                "id": s.id,
                "text": s.text,
                "start": s.start,
                "end": s.end,
                "confidence": s.confidence,
            }
            for s in result.segments
        ]
        words = [
            {
                "text": w.text,
                "start": w.start,
                "end": w.end,
                "confidence": w.confidence,
            }
            for w in result.words
        ] if word_timestamps else None

        return TranscriptionResponse(
            id=str(uuid.uuid4()),
            status=TranscriptionStatus.COMPLETED,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            audio_duration=result.duration,
            text=result.text,
            segments=segments,
            words=words,
            language_code=result.language,
            language_confidence=result.language_confidence,
        )

    finally:
        temp_path.unlink(missing_ok=True)


@router.delete(
    "/transcriptions/{transcription_id}",
    status_code=204,
    summary="Delete transcription",
    description="Delete a transcription and its associated data.",
)
async def delete_transcription(
    transcription_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """
    Delete a transcription.

    Removes the transcription record and associated audio file.
    """
    trans_repo = TranscriptionRepository(db)
    storage = get_storage_backend(settings)

    transcription = await trans_repo.get_by_id(uuid.UUID(transcription_id))
    if transcription is None:
        raise TranscriptionNotFoundError(transcription_id)

    if transcription.user_id != user.user_id:
        raise TranscriptionNotFoundError(transcription_id)

    # Delete audio from storage
    if transcription.audio_storage_key:
        await storage.delete(transcription.audio_storage_key)

    # Delete record
    await trans_repo.delete(transcription.id)
    await db.commit()

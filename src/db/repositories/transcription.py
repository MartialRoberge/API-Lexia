"""
Repository for Transcription operations.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Transcription


class TranscriptionRepository:
    """Repository for transcription CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        job_id: uuid.UUID | None = None,
        audio_url: str | None = None,
        audio_storage_key: str | None = None,
        language_code: str | None = None,
        speaker_diarization: bool = False,
        word_timestamps: bool = True,
        user_id: str | None = None,
        api_key_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Transcription:
        """Create a new transcription."""
        transcription = Transcription(
            job_id=job_id,
            status="processing",
            audio_url=audio_url,
            audio_storage_key=audio_storage_key,
            language_code=language_code,
            speaker_diarization=speaker_diarization,
            word_timestamps=word_timestamps,
            user_id=user_id,
            api_key_id=api_key_id,
            metadata=metadata,
        )
        self.session.add(transcription)
        await self.session.flush()
        return transcription

    async def get_by_id(self, transcription_id: uuid.UUID) -> Transcription | None:
        """Get transcription by ID."""
        result = await self.session.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        return result.scalar_one_or_none()

    async def get_by_job_id(self, job_id: uuid.UUID) -> Transcription | None:
        """Get transcription by job ID."""
        result = await self.session.execute(
            select(Transcription).where(Transcription.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Transcription]:
        """Get transcriptions for a user."""
        query = select(Transcription).where(Transcription.user_id == user_id)

        if status:
            query = query.where(Transcription.status == status)

        query = query.order_by(Transcription.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        transcription_id: uuid.UUID,
        status: str,
        error: str | None = None,
    ) -> None:
        """Update transcription status."""
        values: dict[str, Any] = {"status": status}

        if status == "completed":
            values["completed_at"] = datetime.now(timezone.utc)
        if error:
            values["error"] = error

        await self.session.execute(
            update(Transcription)
            .where(Transcription.id == transcription_id)
            .values(**values)
        )

    async def set_audio_info(
        self,
        transcription_id: uuid.UUID,
        duration: float,
        format: str,
    ) -> None:
        """Set audio information."""
        await self.session.execute(
            update(Transcription)
            .where(Transcription.id == transcription_id)
            .values(
                audio_duration=duration,
                audio_format=format,
            )
        )

    async def set_result(
        self,
        transcription_id: uuid.UUID,
        text: str,
        segments: list[dict[str, Any]] | None = None,
        words: list[dict[str, Any]] | None = None,
        language_detected: str | None = None,
        language_confidence: float | None = None,
        processing_time: float | None = None,
    ) -> None:
        """Set transcription result."""
        values: dict[str, Any] = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "text": text,
        }

        if segments:
            values["segments"] = segments
        if words:
            values["words"] = words
        if language_detected:
            values["language_detected"] = language_detected
        if language_confidence:
            values["language_confidence"] = language_confidence
        if processing_time:
            values["processing_time"] = processing_time

        await self.session.execute(
            update(Transcription)
            .where(Transcription.id == transcription_id)
            .values(**values)
        )

    async def set_diarization_result(
        self,
        transcription_id: uuid.UUID,
        speakers: list[str],
        utterances: list[dict[str, Any]],
        diarization_segments: list[dict[str, Any]] | None = None,
        diarization_stats: dict[str, Any] | None = None,
    ) -> None:
        """Set diarization result."""
        values: dict[str, Any] = {
            "speakers": speakers,
            "utterances": utterances,
        }

        if diarization_segments:
            values["diarization_segments"] = diarization_segments
        if diarization_stats:
            values["diarization_stats"] = diarization_stats

        await self.session.execute(
            update(Transcription)
            .where(Transcription.id == transcription_id)
            .values(**values)
        )

    async def delete(self, transcription_id: uuid.UUID) -> bool:
        """Delete a transcription."""
        transcription = await self.get_by_id(transcription_id)
        if transcription:
            await self.session.delete(transcription)
            return True
        return False

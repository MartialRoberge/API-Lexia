"""
Transcription tasks for Celery.
"""

import asyncio
import tempfile
import time
import uuid
from pathlib import Path

from src.workers.celery_app import app


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(
    bind=True,
    name="src.workers.tasks.transcription.process_transcription",
    max_retries=3,
    default_retry_delay=60,
)
def process_transcription(
    self,
    job_id: str,
    audio_storage_key: str,
    language: str | None = None,
    speaker_diarization: bool = False,
    word_timestamps: bool = True,
):
    """
    Process audio transcription.

    Args:
        job_id: Job UUID string.
        audio_storage_key: Storage key for audio file.
        language: Language code (auto-detect if None).
        speaker_diarization: Enable speaker diarization.
        word_timestamps: Include word-level timestamps.
    """
    return run_async(
        _process_transcription_async(
            self,
            job_id,
            audio_storage_key,
            language,
            speaker_diarization,
            word_timestamps,
        )
    )


async def _process_transcription_async(
    task,
    job_id: str,
    audio_storage_key: str,
    language: str | None,
    speaker_diarization: bool,
    word_timestamps: bool,
):
    """Async implementation of transcription processing."""
    from src.core.config import get_settings
    from src.core.logging import get_logger
    from src.db.repositories.job import JobRepository
    from src.db.repositories.transcription import TranscriptionRepository
    from src.db.session import get_db_context
    from src.services.diarization.factory import get_diarization_backend
    from src.services.stt.factory import get_stt_backend
    from src.services.storage.factory import get_storage_backend

    logger = get_logger(__name__)
    settings = get_settings()

    logger.info(
        "transcription_task_started",
        job_id=job_id,
        audio_key=audio_storage_key,
    )

    start_time = time.time()

    try:
        async with get_db_context() as db:
            job_repo = JobRepository(db)
            trans_repo = TranscriptionRepository(db)

            # Update job status
            job_uuid = uuid.UUID(job_id)
            await job_repo.update_status(job_uuid, "processing")
            await job_repo.update_progress(job_uuid, 10, "Downloading audio")

            # Get transcription record
            transcription = await trans_repo.get_by_job_id(job_uuid)
            if not transcription:
                raise ValueError(f"Transcription not found for job {job_id}")

            # Download audio file
            storage = get_storage_backend(settings)
            audio_data = await storage.download(audio_storage_key)

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                temp_path = Path(f.name)

            try:
                await job_repo.update_progress(job_uuid, 20, "Transcribing audio")

                # Run transcription
                stt_backend = get_stt_backend(settings)
                result = await stt_backend.transcribe(
                    temp_path,
                    language=language,
                    word_timestamps=word_timestamps,
                )

                await job_repo.update_progress(job_uuid, 60, "Processing results")

                # Save transcription result
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
                ]

                await trans_repo.set_result(
                    transcription.id,
                    text=result.text,
                    segments=segments,
                    words=words if word_timestamps else None,
                    language_detected=result.language,
                    language_confidence=result.language_confidence,
                    processing_time=time.time() - start_time,
                )

                # Run diarization if requested
                if speaker_diarization:
                    await job_repo.update_progress(job_uuid, 70, "Diarizing speakers")

                    diarization_backend = get_diarization_backend(settings)
                    diar_result = await diarization_backend.diarize(temp_path)

                    speakers = [s.id for s in diar_result.speakers]
                    utterances = []

                    # TODO: Merge transcription with diarization
                    # For now, just save diarization segments

                    diar_segments = [
                        {
                            "speaker": s.speaker,
                            "start": s.start,
                            "end": s.end,
                            "confidence": s.confidence,
                        }
                        for s in diar_result.segments
                    ]

                    diar_stats = None
                    if diar_result.stats:
                        diar_stats = {
                            "num_speakers": diar_result.stats.num_speakers,
                            "num_segments": diar_result.stats.num_segments,
                            "audio_duration": diar_result.stats.audio_duration,
                        }

                    await trans_repo.set_diarization_result(
                        transcription.id,
                        speakers=speakers,
                        utterances=utterances,
                        diarization_segments=diar_segments,
                        diarization_stats=diar_stats,
                    )

                await job_repo.update_progress(job_uuid, 100, "Completed")
                await job_repo.set_result(
                    job_uuid,
                    result={"transcription_id": str(transcription.id)},
                )

                logger.info(
                    "transcription_task_completed",
                    job_id=job_id,
                    duration=time.time() - start_time,
                )

                return {"status": "success", "transcription_id": str(transcription.id)}

            finally:
                temp_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(
            "transcription_task_failed",
            job_id=job_id,
            error=str(e),
        )

        # Update job as failed
        async with get_db_context() as db:
            job_repo = JobRepository(db)
            await job_repo.update_status(
                uuid.UUID(job_id),
                "failed",
                error_message=str(e),
                error_code="TRANSCRIPTION_ERROR",
            )

        # Retry if applicable
        raise task.retry(exc=e)


@app.task(
    name="src.workers.tasks.transcription.process_transcription_url",
    max_retries=3,
)
def process_transcription_url(
    job_id: str,
    audio_url: str,
    language: str | None = None,
    speaker_diarization: bool = False,
):
    """
    Process transcription from URL.

    Downloads audio from URL first, then processes.
    """
    return run_async(
        _process_transcription_url_async(
            job_id, audio_url, language, speaker_diarization
        )
    )


async def _process_transcription_url_async(
    job_id: str,
    audio_url: str,
    language: str | None,
    speaker_diarization: bool,
):
    """Download audio from URL and process."""
    import httpx

    from src.core.config import get_settings
    from src.db.repositories.job import JobRepository
    from src.db.session import get_db_context
    from src.services.storage.factory import get_storage_backend

    settings = get_settings()

    async with get_db_context() as db:
        job_repo = JobRepository(db)
        await job_repo.update_progress(
            uuid.UUID(job_id), 5, "Downloading from URL"
        )

    # Download audio
    async with httpx.AsyncClient() as client:
        response = await client.get(audio_url, follow_redirects=True)
        response.raise_for_status()
        audio_data = response.content

    # Upload to storage
    storage = get_storage_backend(settings)
    storage_key = storage.generate_key("audio.wav", prefix="transcriptions")
    await storage.upload(storage_key, audio_data)

    # Call main transcription task
    return process_transcription(
        job_id,
        storage_key,
        language,
        speaker_diarization,
    )

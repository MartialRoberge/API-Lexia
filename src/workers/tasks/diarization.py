"""
Diarization tasks for Celery.
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
    name="src.workers.tasks.diarization.process_diarization",
    max_retries=3,
    default_retry_delay=60,
)
def process_diarization(
    self,
    job_id: str,
    audio_storage_key: str,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
):
    """
    Process speaker diarization.

    Args:
        job_id: Job UUID string.
        audio_storage_key: Storage key for audio file.
        num_speakers: Exact number of speakers.
        min_speakers: Minimum speakers.
        max_speakers: Maximum speakers.
    """
    return run_async(
        _process_diarization_async(
            self,
            job_id,
            audio_storage_key,
            num_speakers,
            min_speakers,
            max_speakers,
        )
    )


async def _process_diarization_async(
    task,
    job_id: str,
    audio_storage_key: str,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
):
    """Async implementation of diarization processing."""
    from src.core.config import get_settings
    from src.core.logging import get_logger
    from src.db.repositories.job import JobRepository
    from src.db.session import get_db_context
    from src.services.diarization.factory import get_diarization_backend
    from src.services.storage.factory import get_storage_backend

    logger = get_logger(__name__)
    settings = get_settings()

    logger.info(
        "diarization_task_started",
        job_id=job_id,
        audio_key=audio_storage_key,
    )

    start_time = time.time()

    try:
        async with get_db_context() as db:
            job_repo = JobRepository(db)

            job_uuid = uuid.UUID(job_id)
            await job_repo.update_status(job_uuid, "processing")
            await job_repo.update_progress(job_uuid, 10, "Downloading audio")

            # Download audio file
            storage = get_storage_backend(settings)
            audio_data = await storage.download(audio_storage_key)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                temp_path = Path(f.name)

            try:
                await job_repo.update_progress(job_uuid, 30, "Processing diarization")

                # Run diarization
                diarization_backend = get_diarization_backend(settings)
                result = await diarization_backend.diarize(
                    temp_path,
                    num_speakers=num_speakers,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )

                await job_repo.update_progress(job_uuid, 90, "Finalizing")

                # Prepare result
                speakers = [
                    {
                        "id": s.id,
                        "label": s.label,
                        "total_duration": s.total_duration,
                        "num_segments": s.num_segments,
                    }
                    for s in result.speakers
                ]

                segments = [
                    {
                        "speaker": s.speaker,
                        "start": s.start,
                        "end": s.end,
                        "confidence": s.confidence,
                    }
                    for s in result.segments
                ]

                stats = None
                if result.stats:
                    stats = {
                        "num_speakers": result.stats.num_speakers,
                        "num_segments": result.stats.num_segments,
                        "audio_duration": result.stats.audio_duration,
                        "processing_time": result.stats.processing_time,
                    }

                job_result = {
                    "speakers": speakers,
                    "segments": segments,
                    "stats": stats,
                    "rttm": result.rttm,
                }

                await job_repo.set_result(job_uuid, result=job_result)

                logger.info(
                    "diarization_task_completed",
                    job_id=job_id,
                    speakers=len(speakers),
                    duration=time.time() - start_time,
                )

                return {"status": "success", "speakers": len(speakers)}

            finally:
                temp_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(
            "diarization_task_failed",
            job_id=job_id,
            error=str(e),
        )

        async with get_db_context() as db:
            job_repo = JobRepository(db)
            await job_repo.update_status(
                uuid.UUID(job_id),
                "failed",
                error_message=str(e),
                error_code="DIARIZATION_ERROR",
            )

        raise task.retry(exc=e)

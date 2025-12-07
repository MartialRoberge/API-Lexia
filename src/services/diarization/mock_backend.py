"""
Mock diarization backend for development and testing.
"""

import asyncio
from pathlib import Path

from src.core.logging import get_logger
from src.models.stt import DiarizationStats, OverlapSegment, Speaker, SpeakerSegment
from src.services.diarization.base import DiarizationBackend, DiarizationResult

logger = get_logger(__name__)


class MockDiarizationBackend(DiarizationBackend):
    """Mock diarization backend for development."""

    def __init__(self, response_delay: float = 0.5) -> None:
        self.response_delay = response_delay

    def _generate_mock_result(self, duration: float) -> DiarizationResult:
        """Generate mock diarization result."""
        # Create 2-3 mock speakers
        num_speakers = 2
        speakers = []
        segments = []

        # Generate alternating segments
        current_time = 0.0
        segment_duration = duration / 8  # 8 segments total

        for i in range(8):
            speaker_id = f"SPEAKER_{i % num_speakers:02d}"
            end_time = min(current_time + segment_duration, duration)

            segments.append(
                SpeakerSegment(
                    speaker=speaker_id,
                    start=current_time,
                    end=end_time,
                    confidence=0.95,
                )
            )
            current_time = end_time

        # Compute speaker stats
        speaker_stats = self.compute_speaker_stats(segments)
        speakers = list(speaker_stats.values())

        # Add one mock overlap
        overlaps = []
        if len(segments) > 2:
            overlaps.append(
                OverlapSegment(
                    speakers=["SPEAKER_00", "SPEAKER_01"],
                    start=segments[1].end - 0.5,
                    end=segments[1].end,
                    duration=0.5,
                )
            )

        stats = DiarizationStats(
            version="1.0-mock",
            model="mock-diarization",
            audio_duration=duration,
            num_speakers=num_speakers,
            num_segments=len(segments),
            num_overlaps=len(overlaps),
            overlap_duration=sum(o.duration for o in overlaps),
            processing_time=self.response_delay,
        )

        rttm = self.generate_rttm(segments, "mock_audio")

        return DiarizationResult(
            speakers=speakers,
            segments=segments,
            overlaps=overlaps,
            stats=stats,
            rttm=rttm,
        )

    async def diarize(
        self,
        audio_path: Path | str,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        min_segment_duration: float = 0.0,
        merge_gaps: float = 0.0,
        **kwargs: object,
    ) -> DiarizationResult:
        """Generate mock diarization."""
        logger.info("mock_diarization", audio_path=str(audio_path))

        await asyncio.sleep(self.response_delay)

        # Estimate duration (mock: 60 seconds)
        duration = 60.0
        return self._generate_mock_result(duration)

    async def diarize_bytes(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        **kwargs: object,
    ) -> DiarizationResult:
        """Generate mock diarization from bytes."""
        logger.info("mock_diarization_bytes", size=len(audio_data))

        await asyncio.sleep(self.response_delay)

        duration = len(audio_data) / (16000 * 2)
        return self._generate_mock_result(duration)

    async def health_check(self) -> bool:
        """Mock backend is always healthy."""
        return True

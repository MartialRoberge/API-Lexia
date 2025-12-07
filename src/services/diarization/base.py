"""
Abstract base class for Speaker Diarization backends.

Provides a consistent interface for speaker diarization across different backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from src.models.stt import DiarizationStats, OverlapSegment, Speaker, SpeakerSegment


@dataclass
class DiarizationResult:
    """Internal result from speaker diarization."""

    speakers: list[Speaker] = field(default_factory=list)
    segments: list[SpeakerSegment] = field(default_factory=list)
    overlaps: list[OverlapSegment] = field(default_factory=list)
    stats: DiarizationStats | None = None
    rttm: str | None = None  # RTTM format output


class DiarizationBackend(ABC):
    """Abstract base class for speaker diarization backends."""

    @abstractmethod
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
        """
        Perform speaker diarization on an audio file.

        Args:
            audio_path: Path to the audio file.
            num_speakers: Exact number of speakers (if known).
            min_speakers: Minimum number of speakers.
            max_speakers: Maximum number of speakers.
            min_segment_duration: Minimum segment duration in seconds.
            merge_gaps: Merge segments with gaps smaller than this (seconds).
            **kwargs: Additional backend-specific options.

        Returns:
            DiarizationResult with speaker segments and statistics.

        Raises:
            DiarizationServiceError: If diarization fails.
        """
        ...

    @abstractmethod
    async def diarize_bytes(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        **kwargs: object,
    ) -> DiarizationResult:
        """
        Perform diarization on audio from bytes.

        Args:
            audio_data: Raw audio data.
            audio_format: Audio format (wav, mp3, etc.).
            num_speakers: Exact number of speakers.
            min_speakers: Minimum speakers.
            max_speakers: Maximum speakers.
            **kwargs: Additional options.

        Returns:
            DiarizationResult.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the diarization backend is healthy.

        Returns:
            True if backend is operational.
        """
        ...

    def generate_rttm(
        self,
        segments: list[SpeakerSegment],
        audio_id: str = "audio",
    ) -> str:
        """
        Generate RTTM format output from segments.

        RTTM (Rich Transcription Time Marked) format:
        SPEAKER <file> 1 <start> <duration> <NA> <NA> <speaker> <NA> <NA>

        Args:
            segments: List of speaker segments.
            audio_id: Audio file identifier.

        Returns:
            RTTM formatted string.
        """
        lines = []
        for seg in segments:
            duration = seg.end - seg.start
            line = f"SPEAKER {audio_id} 1 {seg.start:.3f} {duration:.3f} <NA> <NA> {seg.speaker} <NA> <NA>"
            lines.append(line)
        return "\n".join(lines)

    def compute_speaker_stats(
        self,
        segments: list[SpeakerSegment],
    ) -> dict[str, Speaker]:
        """
        Compute statistics per speaker.

        Args:
            segments: List of speaker segments.

        Returns:
            Dictionary mapping speaker ID to Speaker with stats.
        """
        speaker_data: dict[str, list[SpeakerSegment]] = {}

        for seg in segments:
            if seg.speaker not in speaker_data:
                speaker_data[seg.speaker] = []
            speaker_data[seg.speaker].append(seg)

        speakers = {}
        for speaker_id, segs in speaker_data.items():
            total_duration = sum(s.end - s.start for s in segs)
            avg_duration = total_duration / len(segs) if segs else 0

            speakers[speaker_id] = Speaker(
                id=speaker_id,
                total_duration=total_duration,
                num_segments=len(segs),
                avg_segment_duration=avg_duration,
            )

        return speakers

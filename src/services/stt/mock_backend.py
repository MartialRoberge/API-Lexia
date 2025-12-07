"""
Mock STT backend for development and testing.

Provides simulated transcription without requiring actual audio processing.
"""

import asyncio
from pathlib import Path
from typing import AsyncIterator

from src.core.logging import get_logger
from src.models.stt import StreamingTranscriptChunk, TranscriptionSegment, TranscriptionWord
from src.services.stt.base import AudioInfo, STTBackend, TranscriptionResult

logger = get_logger(__name__)


# Sample mock transcriptions
MOCK_TRANSCRIPTS = [
    {
        "text": "Bonjour, bienvenue dans cette réunion. Nous allons discuter des projets en cours.",
        "language": "fr",
        "duration": 5.2,
    },
    {
        "text": "Je pense que nous devrions commencer par le point numéro un de l'ordre du jour.",
        "language": "fr",
        "duration": 4.8,
    },
    {
        "text": "Hello everyone, thank you for joining this meeting today.",
        "language": "en",
        "duration": 3.5,
    },
]


class MockSTTBackend(STTBackend):
    """
    Mock STT backend for development.

    Generates simulated transcription results without actual processing.
    """

    def __init__(
        self,
        response_delay: float = 0.5,
        default_language: str = "fr",
    ) -> None:
        """
        Initialize mock backend.

        Args:
            response_delay: Delay before returning results (seconds).
            default_language: Default language for mock transcripts.
        """
        self.response_delay = response_delay
        self.default_language = default_language
        self._request_count = 0

    def _generate_mock_transcript(
        self, duration: float, language: str
    ) -> TranscriptionResult:
        """Generate mock transcription."""
        self._request_count += 1
        mock = MOCK_TRANSCRIPTS[self._request_count % len(MOCK_TRANSCRIPTS)]

        # Generate words with timing
        words = []
        text = mock["text"]
        word_list = text.split()
        time_per_word = duration / len(word_list)

        for i, word in enumerate(word_list):
            start = i * time_per_word
            end = start + time_per_word * 0.9
            words.append(
                TranscriptionWord(
                    text=word,
                    start=start,
                    end=end,
                    confidence=0.95,
                )
            )

        # Generate segments
        segments = [
            TranscriptionSegment(
                id=0,
                text=text,
                start=0.0,
                end=duration,
                confidence=0.95,
                words=words,
            )
        ]

        return TranscriptionResult(
            text=text,
            segments=segments,
            words=words,
            language=language,
            language_confidence=0.98,
            duration=duration,
        )

    async def transcribe(
        self,
        audio_path: Path | str,
        language: str | None = None,
        word_timestamps: bool = True,
        **kwargs: object,
    ) -> TranscriptionResult:
        """Generate mock transcription."""
        logger.info("mock_stt_transcribe", audio_path=str(audio_path))

        # Simulate processing time
        await asyncio.sleep(self.response_delay)

        # Get audio info for duration
        audio_info = await self.get_audio_info(audio_path)

        return self._generate_mock_transcript(
            audio_info.duration,
            language or self.default_language,
        )

    async def transcribe_bytes(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: str | None = None,
        word_timestamps: bool = True,
        **kwargs: object,
    ) -> TranscriptionResult:
        """Generate mock transcription from bytes."""
        logger.info("mock_stt_transcribe_bytes", size=len(audio_data))

        await asyncio.sleep(self.response_delay)

        # Estimate duration from bytes (rough approximation)
        # Assuming 16kHz, 16-bit mono audio
        estimated_duration = len(audio_data) / (16000 * 2)

        return self._generate_mock_transcript(
            estimated_duration,
            language or self.default_language,
        )

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int = 16000,
        language: str | None = None,
        **kwargs: object,
    ) -> AsyncIterator[StreamingTranscriptChunk]:
        """Generate mock streaming transcription."""
        logger.info("mock_stt_stream")

        chunk_count = 0
        total_bytes = 0

        async for chunk in audio_stream:
            total_bytes += len(chunk)
            chunk_count += 1

            # Emit a mock partial result every few chunks
            if chunk_count % 5 == 0:
                yield StreamingTranscriptChunk(
                    type="partial",
                    text=f"[Mock partial transcript {chunk_count}]",
                    start=0,
                    end=float(chunk_count),
                    confidence=0.9,
                    is_final=False,
                )

        # Final result
        yield StreamingTranscriptChunk(
            type="final",
            text="Ceci est une transcription simulée en mode développement.",
            start=0,
            end=total_bytes / (sample_rate * 2),
            confidence=0.95,
            is_final=True,
        )

    async def get_audio_info(self, audio_path: Path | str) -> AudioInfo:
        """Get mock audio info."""
        path = Path(audio_path)

        # Return mock info based on file size
        if path.exists():
            size = path.stat().st_size
            # Estimate duration assuming 16kHz, 16-bit mono
            duration = size / (16000 * 2)
        else:
            size = 0
            duration = 10.0  # Default mock duration

        return AudioInfo(
            duration=duration,
            sample_rate=16000,
            channels=1,
            format=path.suffix.lstrip(".") or "wav",
            size_bytes=size,
        )

    async def health_check(self) -> bool:
        """Mock backend is always healthy."""
        return True

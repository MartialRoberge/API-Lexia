"""
Whisper backend for STT.

Connects to a Whisper service running as a separate container.
Can also run locally using faster-whisper for development.
"""

import tempfile
from pathlib import Path
from typing import AsyncIterator

import httpx
import librosa
import soundfile as sf

from src.core.exceptions import STTServiceError
from src.core.logging import get_logger
from src.models.stt import StreamingTranscriptChunk, TranscriptionSegment, TranscriptionWord
from src.services.stt.base import AudioInfo, STTBackend, TranscriptionResult

logger = get_logger(__name__)


class WhisperBackend(STTBackend):
    """
    Whisper STT backend.

    Uses the faster-whisper library or connects to a remote service.
    """

    def __init__(
        self,
        model_name: str = "Gilbert-AI/gilbert-fr-source",
        device: str = "cuda",
        compute_type: str = "float16",
        service_url: str | None = None,
    ) -> None:
        """
        Initialize Whisper backend.

        Args:
            model_name: Hugging Face model name.
            device: Device to run on (cuda/cpu).
            compute_type: Compute type (float16/float32/int8).
            service_url: URL of remote STT service (if using service mode).
        """
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.service_url = service_url
        self._model = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client for service mode."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.service_url or "",
                timeout=httpx.Timeout(300.0),  # 5 min timeout for long audio
            )
        return self._client

    def _load_model(self) -> object:
        """Load Whisper model (lazy loading)."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel

                logger.info("loading_whisper_model", model=self.model_name)
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                logger.info("whisper_model_loaded", model=self.model_name)
            except Exception as e:
                raise STTServiceError(
                    message=f"Failed to load Whisper model: {e}",
                    details={"model": self.model_name},
                ) from e
        return self._model

    async def transcribe(
        self,
        audio_path: Path | str,
        language: str | None = None,
        word_timestamps: bool = True,
        **kwargs: object,
    ) -> TranscriptionResult:
        """Transcribe audio file."""
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise STTServiceError(
                message=f"Audio file not found: {audio_path}",
            )

        # Use service mode if URL is configured
        if self.service_url:
            return await self._transcribe_via_service(
                audio_path, language, word_timestamps
            )

        # Local mode with faster-whisper
        return await self._transcribe_local(audio_path, language, word_timestamps)

    async def _transcribe_local(
        self,
        audio_path: Path,
        language: str | None,
        word_timestamps: bool,
    ) -> TranscriptionResult:
        """Transcribe using local Whisper model."""
        import asyncio

        model = self._load_model()

        def _run_transcription() -> TranscriptionResult:
            # Run transcription
            segments_gen, info = model.transcribe(
                str(audio_path),
                language=language,
                word_timestamps=word_timestamps,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )

            # Collect results
            full_text = []
            segments: list[TranscriptionSegment] = []
            all_words: list[TranscriptionWord] = []

            for i, segment in enumerate(segments_gen):
                full_text.append(segment.text.strip())

                words = []
                if word_timestamps and segment.words:
                    for word in segment.words:
                        word_obj = TranscriptionWord(
                            text=word.word,
                            start=word.start,
                            end=word.end,
                            confidence=word.probability,
                        )
                        words.append(word_obj)
                        all_words.append(word_obj)

                segments.append(
                    TranscriptionSegment(
                        id=i,
                        text=segment.text.strip(),
                        start=segment.start,
                        end=segment.end,
                        confidence=sum(w.probability for w in (segment.words or []))
                        / max(len(segment.words or []), 1),
                        words=words if words else None,
                    )
                )

            return TranscriptionResult(
                text=" ".join(full_text),
                segments=segments,
                words=all_words,
                language=info.language,
                language_confidence=info.language_probability,
                duration=info.duration,
            )

        # Run in thread pool to not block async
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_transcription)

        logger.info(
            "transcription_complete",
            duration=result.duration,
            language=result.language,
            segments=len(result.segments),
        )

        return result

    async def _transcribe_via_service(
        self,
        audio_path: Path,
        language: str | None,
        word_timestamps: bool,
    ) -> TranscriptionResult:
        """Transcribe using remote STT service."""
        try:
            client = await self._get_client()

            # Upload audio and get transcription
            with open(audio_path, "rb") as f:
                files = {"audio": (audio_path.name, f, "audio/wav")}
                params = {
                    "word_timestamps": word_timestamps,
                }
                if language:
                    params["language"] = language

                response = await client.post(
                    "/transcribe",
                    files=files,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            # Parse response
            segments = []
            words = []
            for seg in data.get("segments", []):
                seg_words = []
                for w in seg.get("words", []):
                    word = TranscriptionWord(
                        text=w["text"],
                        start=w["start"],
                        end=w["end"],
                        confidence=w.get("confidence", 1.0),
                    )
                    seg_words.append(word)
                    words.append(word)

                segments.append(
                    TranscriptionSegment(
                        id=seg["id"],
                        text=seg["text"],
                        start=seg["start"],
                        end=seg["end"],
                        confidence=seg.get("confidence", 1.0),
                        words=seg_words if seg_words else None,
                    )
                )

            return TranscriptionResult(
                text=data.get("text", ""),
                segments=segments,
                words=words,
                language=data.get("language", "fr"),
                language_confidence=data.get("language_confidence", 1.0),
                duration=data.get("duration", 0.0),
            )

        except httpx.HTTPStatusError as e:
            raise STTServiceError(
                message=f"STT service error: {e.response.text}",
            ) from e
        except httpx.RequestError as e:
            raise STTServiceError(
                message=f"Failed to connect to STT service: {e}",
            ) from e

    async def transcribe_bytes(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: str | None = None,
        word_timestamps: bool = True,
        **kwargs: object,
    ) -> TranscriptionResult:
        """Transcribe audio from bytes."""
        # Save to temp file
        with tempfile.NamedTemporaryFile(
            suffix=f".{audio_format}", delete=False
        ) as f:
            f.write(audio_data)
            temp_path = Path(f.name)

        try:
            return await self.transcribe(
                temp_path, language, word_timestamps, **kwargs
            )
        finally:
            temp_path.unlink(missing_ok=True)

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int = 16000,
        language: str | None = None,
        **kwargs: object,
    ) -> AsyncIterator[StreamingTranscriptChunk]:
        """
        Transcribe streaming audio.

        Note: Real streaming requires WebSocket support.
        This implementation buffers and processes in chunks.
        """
        buffer = bytearray()
        chunk_duration = 5.0  # Process every 5 seconds of audio
        bytes_per_second = sample_rate * 2  # 16-bit audio
        chunk_size = int(chunk_duration * bytes_per_second)

        async for audio_chunk in audio_stream:
            buffer.extend(audio_chunk)

            if len(buffer) >= chunk_size:
                # Process chunk
                chunk_data = bytes(buffer[:chunk_size])
                buffer = buffer[chunk_size:]

                # Transcribe chunk
                result = await self.transcribe_bytes(
                    chunk_data,
                    audio_format="wav",
                    language=language,
                )

                if result.text.strip():
                    yield StreamingTranscriptChunk(
                        type="partial",
                        text=result.text,
                        start=0,  # Would need proper timestamp tracking
                        end=chunk_duration,
                        confidence=result.language_confidence,
                        is_final=False,
                    )

        # Process remaining buffer
        if buffer:
            result = await self.transcribe_bytes(
                bytes(buffer),
                audio_format="wav",
                language=language,
            )
            if result.text.strip():
                yield StreamingTranscriptChunk(
                    type="final",
                    text=result.text,
                    start=0,
                    end=len(buffer) / bytes_per_second,
                    confidence=result.language_confidence,
                    is_final=True,
                )

    async def get_audio_info(self, audio_path: Path | str) -> AudioInfo:
        """Get audio file information."""
        import asyncio

        audio_path = Path(audio_path)

        def _get_info() -> AudioInfo:
            # Load audio metadata
            info = sf.info(str(audio_path))
            return AudioInfo(
                duration=info.duration,
                sample_rate=info.samplerate,
                channels=info.channels,
                format=info.format,
                size_bytes=audio_path.stat().st_size,
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_info)

    async def health_check(self) -> bool:
        """Check if Whisper backend is healthy."""
        if self.service_url:
            try:
                client = await self._get_client()
                response = await client.get("/health")
                return response.status_code == 200
            except Exception:
                return False
        else:
            # Local mode - check if model can be loaded
            try:
                self._load_model()
                return True
            except Exception:
                return False

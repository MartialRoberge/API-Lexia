"""
Pyannote backend for speaker diarization.

Uses pyannote.audio for speaker diarization.
"""

import tempfile
import time
from pathlib import Path

import httpx

from src.core.exceptions import DiarizationServiceError
from src.core.logging import get_logger
from src.models.stt import DiarizationStats, OverlapSegment, SpeakerSegment
from src.services.diarization.base import DiarizationBackend, DiarizationResult

logger = get_logger(__name__)


class PyannoteBackend(DiarizationBackend):
    """
    Pyannote diarization backend.

    Uses the pyannote.audio library or connects to a remote service.
    """

    def __init__(
        self,
        model_name: str = "MEscriva/gilbert-pyannote-diarization",
        hf_token: str | None = None,
        device: str = "cuda",
        service_url: str | None = None,
    ) -> None:
        """
        Initialize Pyannote backend.

        Args:
            model_name: Hugging Face model name.
            hf_token: Hugging Face authentication token.
            device: Device to run on (cuda/cpu).
            service_url: URL of remote service (if using service mode).
        """
        self.model_name = model_name
        self.hf_token = hf_token
        self.device = device
        self.service_url = service_url
        self._pipeline = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client for service mode."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.service_url or "",
                timeout=httpx.Timeout(600.0),  # 10 min timeout
            )
        return self._client

    def _load_pipeline(self) -> object:
        """Load Pyannote pipeline (lazy loading)."""
        if self._pipeline is None:
            try:
                from pyannote.audio import Pipeline
                import torch

                logger.info("loading_pyannote_pipeline", model=self.model_name)

                self._pipeline = Pipeline.from_pretrained(
                    self.model_name,
                    use_auth_token=self.hf_token,
                )

                if self.device == "cuda" and torch.cuda.is_available():
                    self._pipeline.to(torch.device("cuda"))

                logger.info("pyannote_pipeline_loaded", model=self.model_name)

            except Exception as e:
                raise DiarizationServiceError(
                    message=f"Failed to load Pyannote pipeline: {e}",
                    details={"model": self.model_name},
                ) from e
        return self._pipeline

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
        """Perform speaker diarization."""
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise DiarizationServiceError(
                message=f"Audio file not found: {audio_path}",
            )

        # Use service mode if URL is configured
        if self.service_url:
            return await self._diarize_via_service(
                audio_path,
                num_speakers,
                min_speakers,
                max_speakers,
                min_segment_duration,
                merge_gaps,
            )

        # Local mode with pyannote
        return await self._diarize_local(
            audio_path,
            num_speakers,
            min_speakers,
            max_speakers,
            min_segment_duration,
            merge_gaps,
        )

    async def _diarize_local(
        self,
        audio_path: Path,
        num_speakers: int | None,
        min_speakers: int | None,
        max_speakers: int | None,
        min_segment_duration: float,
        merge_gaps: float,
    ) -> DiarizationResult:
        """Diarize using local Pyannote pipeline."""
        import asyncio

        pipeline = self._load_pipeline()
        start_time = time.time()

        def _run_diarization() -> object:
            # Build kwargs for pipeline
            pipeline_kwargs = {}
            if num_speakers is not None:
                pipeline_kwargs["num_speakers"] = num_speakers
            if min_speakers is not None:
                pipeline_kwargs["min_speakers"] = min_speakers
            if max_speakers is not None:
                pipeline_kwargs["max_speakers"] = max_speakers

            # Run diarization
            return pipeline(str(audio_path), **pipeline_kwargs)

        loop = asyncio.get_event_loop()
        diarization = await loop.run_in_executor(None, _run_diarization)

        processing_time = time.time() - start_time

        # Parse results
        segments: list[SpeakerSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            duration = turn.end - turn.start
            if duration >= min_segment_duration:
                segments.append(
                    SpeakerSegment(
                        speaker=speaker,
                        start=turn.start,
                        end=turn.end,
                        confidence=1.0,  # Pyannote doesn't provide per-segment confidence
                    )
                )

        # Merge small gaps
        if merge_gaps > 0:
            segments = self._merge_gaps(segments, merge_gaps)

        # Detect overlaps
        overlaps = self._detect_overlaps(diarization)

        # Compute speaker stats
        speaker_stats = self.compute_speaker_stats(segments)
        speakers = list(speaker_stats.values())

        # Get audio duration
        import librosa
        audio_duration = librosa.get_duration(path=str(audio_path))

        # Compute total overlap duration
        total_overlap = sum(o.duration for o in overlaps)

        stats = DiarizationStats(
            version="1.0",
            model=self.model_name,
            audio_duration=audio_duration,
            num_speakers=len(speakers),
            num_segments=len(segments),
            num_overlaps=len(overlaps),
            overlap_duration=total_overlap,
            processing_time=processing_time,
        )

        # Generate RTTM
        rttm = self.generate_rttm(segments, audio_path.stem)

        logger.info(
            "diarization_complete",
            speakers=len(speakers),
            segments=len(segments),
            processing_time=processing_time,
        )

        return DiarizationResult(
            speakers=speakers,
            segments=segments,
            overlaps=overlaps,
            stats=stats,
            rttm=rttm,
        )

    def _merge_gaps(
        self,
        segments: list[SpeakerSegment],
        max_gap: float,
    ) -> list[SpeakerSegment]:
        """Merge segments from same speaker with small gaps."""
        if not segments:
            return segments

        # Sort by start time
        sorted_segments = sorted(segments, key=lambda s: s.start)
        merged = [sorted_segments[0]]

        for seg in sorted_segments[1:]:
            prev = merged[-1]
            gap = seg.start - prev.end

            if seg.speaker == prev.speaker and gap <= max_gap:
                # Merge with previous
                merged[-1] = SpeakerSegment(
                    speaker=prev.speaker,
                    start=prev.start,
                    end=seg.end,
                    confidence=min(prev.confidence, seg.confidence),
                )
            else:
                merged.append(seg)

        return merged

    def _detect_overlaps(self, diarization: object) -> list[OverlapSegment]:
        """Detect overlapping speech segments."""
        overlaps: list[OverlapSegment] = []

        # Get all turns
        turns = list(diarization.itertracks(yield_label=True))

        for i, (turn1, _, speaker1) in enumerate(turns):
            for turn2, _, speaker2 in turns[i + 1 :]:
                if speaker1 == speaker2:
                    continue

                # Check for overlap
                overlap_start = max(turn1.start, turn2.start)
                overlap_end = min(turn1.end, turn2.end)

                if overlap_start < overlap_end:
                    overlaps.append(
                        OverlapSegment(
                            speakers=[speaker1, speaker2],
                            start=overlap_start,
                            end=overlap_end,
                            duration=overlap_end - overlap_start,
                        )
                    )

        return overlaps

    async def _diarize_via_service(
        self,
        audio_path: Path,
        num_speakers: int | None,
        min_speakers: int | None,
        max_speakers: int | None,
        min_segment_duration: float,
        merge_gaps: float,
    ) -> DiarizationResult:
        """Diarize using remote service."""
        try:
            client = await self._get_client()

            with open(audio_path, "rb") as f:
                files = {"audio": (audio_path.name, f, "audio/wav")}
                params = {
                    "min_segment_duration": min_segment_duration,
                    "merge_gaps": merge_gaps,
                }
                if num_speakers:
                    params["num_speakers"] = num_speakers
                if min_speakers:
                    params["min_speakers"] = min_speakers
                if max_speakers:
                    params["max_speakers"] = max_speakers

                response = await client.post(
                    "/diarize",
                    files=files,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            # Parse response (implementation depends on service format)
            # This is a placeholder - adjust based on actual service response
            return DiarizationResult(
                speakers=[],
                segments=[],
                overlaps=[],
            )

        except httpx.HTTPStatusError as e:
            raise DiarizationServiceError(
                message=f"Diarization service error: {e.response.text}",
            ) from e
        except httpx.RequestError as e:
            raise DiarizationServiceError(
                message=f"Failed to connect to diarization service: {e}",
            ) from e

    async def diarize_bytes(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        **kwargs: object,
    ) -> DiarizationResult:
        """Diarize audio from bytes."""
        with tempfile.NamedTemporaryFile(
            suffix=f".{audio_format}", delete=False
        ) as f:
            f.write(audio_data)
            temp_path = Path(f.name)

        try:
            return await self.diarize(
                temp_path,
                num_speakers,
                min_speakers,
                max_speakers,
                **kwargs,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    async def health_check(self) -> bool:
        """Check if backend is healthy."""
        if self.service_url:
            try:
                client = await self._get_client()
                response = await client.get("/health")
                return response.status_code == 200
            except Exception:
                return False
        else:
            try:
                self._load_pipeline()
                return True
            except Exception:
                return False

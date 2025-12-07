"""
STT and Diarization Microservice Server.

Standalone FastAPI server for Speech-to-Text and Speaker Diarization.
Can be deployed independently and scaled horizontally.

Usage:
    uvicorn src.services.stt.server:app --host 0.0.0.0 --port 8002
"""

import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, File, Query, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# -----------------------------------------------------------------------------
# Configuration from environment
# -----------------------------------------------------------------------------
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "Gilbert-AI/gilbert-fr-source")
DIARIZATION_MODEL = os.environ.get("DIARIZATION_MODEL", "MEscriva/gilbert-pyannote-diarization")
DEVICE = os.environ.get("DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
COMPUTE_TYPE = os.environ.get("COMPUTE_TYPE", "float16" if DEVICE == "cuda" else "float32")
HF_TOKEN = os.environ.get("HF_TOKEN", "")


# -----------------------------------------------------------------------------
# Global model instances (loaded once at startup)
# -----------------------------------------------------------------------------
whisper_model = None
diarization_pipeline = None


# -----------------------------------------------------------------------------
# Response Models
# -----------------------------------------------------------------------------
class TranscriptionWord(BaseModel):
    text: str
    start: float
    end: float
    confidence: float = 1.0


class TranscriptionSegment(BaseModel):
    id: int
    text: str
    start: float
    end: float
    confidence: float = 1.0
    words: list[TranscriptionWord] | None = None


class TranscriptionResponse(BaseModel):
    text: str
    segments: list[TranscriptionSegment]
    words: list[TranscriptionWord]
    language: str
    language_confidence: float
    duration: float


class Speaker(BaseModel):
    id: str
    total_duration: float
    num_segments: int
    percentage: float


class SpeakerSegment(BaseModel):
    speaker: str
    start: float
    end: float
    confidence: float = 1.0


class OverlapSegment(BaseModel):
    speakers: list[str]
    start: float
    end: float
    duration: float


class DiarizationStats(BaseModel):
    version: str = "1.0"
    model: str
    audio_duration: float
    num_speakers: int
    num_segments: int
    num_overlaps: int
    overlap_duration: float
    processing_time: float


class DiarizationResponse(BaseModel):
    speakers: list[Speaker]
    segments: list[SpeakerSegment]
    overlaps: list[OverlapSegment]
    stats: DiarizationStats | None = None
    rttm: str | None = None


class HealthResponse(BaseModel):
    status: str
    whisper_loaded: bool
    diarization_loaded: bool
    device: str


# -----------------------------------------------------------------------------
# Model Loading
# -----------------------------------------------------------------------------
def load_whisper():
    """Load Whisper model."""
    global whisper_model
    if whisper_model is None:
        from faster_whisper import WhisperModel
        print(f"Loading Whisper model: {WHISPER_MODEL} on {DEVICE}")
        whisper_model = WhisperModel(
            WHISPER_MODEL,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
        print("Whisper model loaded successfully")
    return whisper_model


def load_diarization():
    """Load Pyannote diarization pipeline."""
    global diarization_pipeline
    if diarization_pipeline is None:
        from pyannote.audio import Pipeline
        print(f"Loading Diarization model: {DIARIZATION_MODEL}")
        diarization_pipeline = Pipeline.from_pretrained(
            DIARIZATION_MODEL,
            use_auth_token=HF_TOKEN if HF_TOKEN else None,
        )
        if DEVICE == "cuda" and torch.cuda.is_available():
            diarization_pipeline.to(torch.device("cuda"))
        print("Diarization model loaded successfully")
    return diarization_pipeline


# -----------------------------------------------------------------------------
# Lifespan - Load models at startup
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models at startup."""
    print("=" * 50)
    print("  Lexia STT/Diarization Server Starting")
    print("=" * 50)
    print(f"Whisper Model: {WHISPER_MODEL}")
    print(f"Diarization Model: {DIARIZATION_MODEL}")
    print(f"Device: {DEVICE}")
    print(f"Compute Type: {COMPUTE_TYPE}")
    print("=" * 50)

    # Pre-load models
    try:
        load_whisper()
    except Exception as e:
        print(f"Warning: Could not pre-load Whisper: {e}")

    try:
        load_diarization()
    except Exception as e:
        print(f"Warning: Could not pre-load Diarization: {e}")

    yield

    print("Shutting down STT/Diarization server...")


# -----------------------------------------------------------------------------
# FastAPI Application
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Lexia STT/Diarization Service",
    description="Microservice for Speech-to-Text and Speaker Diarization",
    version="1.0.0",
    lifespan=lifespan,
)


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health."""
    return HealthResponse(
        status="healthy" if (whisper_model or diarization_pipeline) else "starting",
        whisper_loaded=whisper_model is not None,
        diarization_loaded=diarization_pipeline is not None,
        device=DEVICE,
    )


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    audio: UploadFile = File(..., description="Audio file to transcribe"),
    language: str | None = Query(None, description="Language code (e.g., 'fr', 'en')"),
    word_timestamps: bool = Query(True, description="Include word-level timestamps"),
) -> TranscriptionResponse:
    """
    Transcribe audio file using Whisper.

    Returns transcription with segments and optional word timestamps.
    """
    # Save uploaded file to temp
    suffix = Path(audio.filename or "audio.wav").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        content = await audio.read()
        f.write(content)
        temp_path = Path(f.name)

    try:
        model = load_whisper()

        # Run transcription
        segments_gen, info = model.transcribe(
            str(temp_path),
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

            avg_confidence = (
                sum(w.probability for w in (segment.words or []))
                / max(len(segment.words or []), 1)
            )

            segments.append(
                TranscriptionSegment(
                    id=i,
                    text=segment.text.strip(),
                    start=segment.start,
                    end=segment.end,
                    confidence=avg_confidence,
                    words=words if words else None,
                )
            )

        return TranscriptionResponse(
            text=" ".join(full_text),
            segments=segments,
            words=all_words,
            language=info.language,
            language_confidence=info.language_probability,
            duration=info.duration,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/diarize", response_model=DiarizationResponse)
async def diarize(
    audio: UploadFile = File(..., description="Audio file for diarization"),
    num_speakers: int | None = Query(None, ge=1, le=20, description="Exact number of speakers"),
    min_speakers: int | None = Query(None, ge=1, description="Minimum number of speakers"),
    max_speakers: int | None = Query(None, le=20, description="Maximum number of speakers"),
    min_segment_duration: float = Query(0.0, ge=0, description="Minimum segment duration"),
    merge_gaps: float = Query(0.0, ge=0, description="Merge gaps smaller than this"),
) -> DiarizationResponse:
    """
    Perform speaker diarization on audio file.

    Returns speaker segments with timing information.
    """
    import librosa

    # Save uploaded file to temp
    suffix = Path(audio.filename or "audio.wav").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        content = await audio.read()
        f.write(content)
        temp_path = Path(f.name)

    try:
        pipeline = load_diarization()
        start_time = time.time()

        # Build kwargs for pipeline
        pipeline_kwargs: dict[str, Any] = {}
        if num_speakers is not None:
            pipeline_kwargs["num_speakers"] = num_speakers
        if min_speakers is not None:
            pipeline_kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            pipeline_kwargs["max_speakers"] = max_speakers

        # Run diarization
        diarization = pipeline(str(temp_path), **pipeline_kwargs)

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
                        confidence=1.0,
                    )
                )

        # Merge small gaps between same speaker
        if merge_gaps > 0:
            segments = _merge_gaps(segments, merge_gaps)

        # Detect overlaps
        overlaps = _detect_overlaps(diarization)

        # Compute speaker stats
        speaker_stats = _compute_speaker_stats(segments)
        speakers = list(speaker_stats.values())

        # Get audio duration
        audio_duration = librosa.get_duration(path=str(temp_path))

        # Compute total overlap duration
        total_overlap = sum(o.duration for o in overlaps)

        stats = DiarizationStats(
            model=DIARIZATION_MODEL,
            audio_duration=audio_duration,
            num_speakers=len(speakers),
            num_segments=len(segments),
            num_overlaps=len(overlaps),
            overlap_duration=total_overlap,
            processing_time=processing_time,
        )

        # Generate RTTM
        rttm = _generate_rttm(segments, temp_path.stem)

        return DiarizationResponse(
            speakers=speakers,
            segments=segments,
            overlaps=overlaps,
            stats=stats,
            rttm=rttm,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diarization failed: {str(e)}")

    finally:
        temp_path.unlink(missing_ok=True)


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def _merge_gaps(segments: list[SpeakerSegment], max_gap: float) -> list[SpeakerSegment]:
    """Merge segments from same speaker with small gaps."""
    if not segments:
        return segments

    sorted_segments = sorted(segments, key=lambda s: s.start)
    merged = [sorted_segments[0]]

    for seg in sorted_segments[1:]:
        prev = merged[-1]
        gap = seg.start - prev.end

        if seg.speaker == prev.speaker and gap <= max_gap:
            merged[-1] = SpeakerSegment(
                speaker=prev.speaker,
                start=prev.start,
                end=seg.end,
                confidence=min(prev.confidence, seg.confidence),
            )
        else:
            merged.append(seg)

    return merged


def _detect_overlaps(diarization) -> list[OverlapSegment]:
    """Detect overlapping speech segments."""
    overlaps: list[OverlapSegment] = []
    turns = list(diarization.itertracks(yield_label=True))

    for i, (turn1, _, speaker1) in enumerate(turns):
        for turn2, _, speaker2 in turns[i + 1:]:
            if speaker1 == speaker2:
                continue

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


def _compute_speaker_stats(segments: list[SpeakerSegment]) -> dict[str, Speaker]:
    """Compute statistics for each speaker."""
    stats: dict[str, dict[str, float | int]] = {}
    total_duration = 0.0

    for seg in segments:
        duration = seg.end - seg.start
        total_duration += duration

        if seg.speaker not in stats:
            stats[seg.speaker] = {"duration": 0.0, "count": 0}

        stats[seg.speaker]["duration"] += duration
        stats[seg.speaker]["count"] += 1

    result = {}
    for speaker_id, data in stats.items():
        result[speaker_id] = Speaker(
            id=speaker_id,
            total_duration=data["duration"],
            num_segments=int(data["count"]),
            percentage=(data["duration"] / total_duration * 100) if total_duration > 0 else 0,
        )

    return result


def _generate_rttm(segments: list[SpeakerSegment], file_id: str) -> str:
    """Generate RTTM format output."""
    lines = []
    for seg in segments:
        duration = seg.end - seg.start
        line = f"SPEAKER {file_id} 1 {seg.start:.3f} {duration:.3f} <NA> <NA> {seg.speaker} <NA> <NA>"
        lines.append(line)
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("STT_PORT", "8002"))
    host = os.environ.get("STT_HOST", "0.0.0.0")

    uvicorn.run(app, host=host, port=port)

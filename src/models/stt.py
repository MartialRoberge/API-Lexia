"""
Pydantic models for Speech-to-Text and Diarization API endpoints.

Inspired by AssemblyAI API format with enhancements for our use case.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator

from src.models.common import StrictBaseModel


class AudioFormat(str, Enum):
    """Supported audio formats."""

    WAV = "wav"
    MP3 = "mp3"
    M4A = "m4a"
    FLAC = "flac"
    OGG = "ogg"
    WEBM = "webm"


class TranscriptionStatus(str, Enum):
    """Status of a transcription job."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LanguageCode(str, Enum):
    """Supported language codes."""

    FR = "fr"  # French
    EN = "en"  # English
    DE = "de"  # German
    ES = "es"  # Spanish
    IT = "it"  # Italian
    PT = "pt"  # Portuguese
    NL = "nl"  # Dutch
    AUTO = "auto"  # Auto-detect


# =============================================================================
# Transcription Models
# =============================================================================


class TranscriptionWord(StrictBaseModel):
    """A word in the transcription with timing information."""

    text: str = Field(..., description="The transcribed word")
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., ge=0, description="End time in seconds")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1)",
    )
    speaker: str | None = Field(
        default=None,
        description="Speaker label (if diarization enabled)",
    )


class TranscriptionSegment(StrictBaseModel):
    """A segment of transcribed text."""

    id: int = Field(..., description="Segment index")
    text: str = Field(..., description="Transcribed text")
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., ge=0, description="End time in seconds")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Average confidence",
    )
    words: list[TranscriptionWord] | None = Field(
        default=None,
        description="Word-level details",
    )
    speaker: str | None = Field(
        default=None,
        description="Speaker label",
    )


class TranscriptionRequest(StrictBaseModel):
    """
    Request for audio transcription.

    Supports both URL-based and file upload methods.
    """

    # Audio source (one of these must be provided)
    audio_url: str | None = Field(
        default=None,
        description="URL of the audio file to transcribe",
    )

    # Language settings
    language_code: LanguageCode = Field(
        default=LanguageCode.FR,
        description="Language of the audio",
    )
    language_detection: bool = Field(
        default=False,
        description="Enable automatic language detection",
    )

    # Transcription options
    punctuate: bool = Field(
        default=True,
        description="Add punctuation to transcript",
    )
    format_text: bool = Field(
        default=True,
        description="Format text (capitalize, etc.)",
    )
    word_timestamps: bool = Field(
        default=True,
        description="Include word-level timestamps",
    )

    # Diarization options
    speaker_diarization: bool = Field(
        default=False,
        description="Enable speaker diarization",
    )
    speakers_expected: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Expected number of speakers",
    )
    min_speakers: int | None = Field(
        default=None,
        ge=1,
        description="Minimum number of speakers",
    )
    max_speakers: int | None = Field(
        default=None,
        le=20,
        description="Maximum number of speakers",
    )

    # Processing mode
    async_mode: bool = Field(
        default=True,
        description="Process asynchronously (recommended for long audio)",
    )

    # Webhook (for async mode)
    webhook_url: str | None = Field(
        default=None,
        description="URL to call when transcription is complete",
    )
    webhook_auth_header: str | None = Field(
        default=None,
        description="Authorization header for webhook",
    )

    # Metadata
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Custom metadata to attach to the transcription",
    )

    @field_validator("audio_url")
    @classmethod
    def validate_audio_url(cls, v: str | None) -> str | None:
        """Validate audio URL format."""
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("audio_url must be a valid HTTP(S) URL")
        return v


class TranscriptionResponse(StrictBaseModel):
    """
    Response from transcription.

    Contains full transcript and optional word/speaker details.
    """

    id: str = Field(..., description="Unique transcription ID")
    status: TranscriptionStatus = Field(..., description="Transcription status")

    # Timing
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: datetime | None = Field(
        default=None,
        description="Completion timestamp",
    )

    # Audio info
    audio_url: str | None = Field(default=None, description="Source audio URL")
    audio_duration: float | None = Field(
        default=None,
        description="Audio duration in seconds",
    )

    # Transcription results
    text: str | None = Field(
        default=None,
        description="Full transcript text",
    )
    segments: list[TranscriptionSegment] | None = Field(
        default=None,
        description="Transcript segments",
    )
    words: list[TranscriptionWord] | None = Field(
        default=None,
        description="Word-level transcript",
    )

    # Language
    language_code: str | None = Field(
        default=None,
        description="Detected or specified language",
    )
    language_confidence: float | None = Field(
        default=None,
        description="Language detection confidence",
    )

    # Diarization results
    speakers: list[str] | None = Field(
        default=None,
        description="List of detected speakers",
    )
    utterances: list["Utterance"] | None = Field(
        default=None,
        description="Speaker-attributed utterances",
    )

    # Error info (if failed)
    error: str | None = Field(
        default=None,
        description="Error message if status is failed",
    )

    # Metadata
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Custom metadata",
    )


class TranscriptionJob(StrictBaseModel):
    """Minimal job info returned when creating async transcription."""

    id: str = Field(..., description="Job ID for polling")
    status: TranscriptionStatus = Field(
        default=TranscriptionStatus.QUEUED,
        description="Current status",
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    estimated_completion: datetime | None = Field(
        default=None,
        description="Estimated completion time",
    )


# =============================================================================
# Diarization Models
# =============================================================================


class Speaker(StrictBaseModel):
    """Information about a detected speaker."""

    id: str = Field(..., description="Speaker identifier (e.g., 'SPEAKER_00')")
    label: str | None = Field(
        default=None,
        description="Custom label if provided",
    )
    total_duration: float = Field(
        default=0.0,
        description="Total speaking time in seconds",
    )
    num_segments: int = Field(
        default=0,
        description="Number of speech segments",
    )
    avg_segment_duration: float = Field(
        default=0.0,
        description="Average segment duration",
    )


class SpeakerSegment(StrictBaseModel):
    """A segment of speech by a speaker."""

    speaker: str = Field(..., description="Speaker identifier")
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., ge=0, description="End time in seconds")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score",
    )


class Utterance(StrictBaseModel):
    """An utterance by a speaker with transcript."""

    speaker: str = Field(..., description="Speaker identifier")
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., ge=0, description="End time in seconds")
    text: str = Field(..., description="Transcribed text")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score",
    )
    words: list[TranscriptionWord] | None = Field(
        default=None,
        description="Word-level details",
    )


class OverlapSegment(StrictBaseModel):
    """A segment where speakers overlap."""

    speakers: list[str] = Field(..., description="Speakers involved")
    start: float = Field(..., ge=0, description="Start time")
    end: float = Field(..., ge=0, description="End time")
    duration: float = Field(..., ge=0, description="Overlap duration")


class DiarizationRequest(StrictBaseModel):
    """Request for speaker diarization only (without transcription)."""

    audio_url: str | None = Field(
        default=None,
        description="URL of the audio file",
    )

    # Speaker settings
    num_speakers: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Exact number of speakers (if known)",
    )
    min_speakers: int | None = Field(
        default=None,
        ge=1,
        description="Minimum number of speakers",
    )
    max_speakers: int | None = Field(
        default=None,
        le=20,
        description="Maximum number of speakers",
    )

    # Processing options
    min_segment_duration: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum segment duration in seconds",
    )
    merge_gaps: float = Field(
        default=0.0,
        ge=0.0,
        description="Merge segments with gaps smaller than this (seconds)",
    )

    # Output format
    output_format: Literal["json", "rttm"] = Field(
        default="json",
        description="Output format for segments",
    )

    # Processing mode
    async_mode: bool = Field(
        default=True,
        description="Process asynchronously",
    )

    # Metadata
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Custom metadata",
    )


class DiarizationStats(StrictBaseModel):
    """Statistics about the diarization results."""

    version: str = Field(default="1.0", description="Diarization model version")
    model: str = Field(..., description="Model used")
    audio_duration: float = Field(..., description="Total audio duration")
    num_speakers: int = Field(..., description="Number of detected speakers")
    num_segments: int = Field(..., description="Total number of segments")
    num_overlaps: int = Field(default=0, description="Number of overlap segments")
    overlap_duration: float = Field(
        default=0.0,
        description="Total overlap duration",
    )
    processing_time: float | None = Field(
        default=None,
        description="Processing time in seconds",
    )


class DiarizationResponse(StrictBaseModel):
    """Response from diarization."""

    id: str = Field(..., description="Unique diarization ID")
    status: TranscriptionStatus = Field(..., description="Processing status")

    # Timing
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: datetime | None = Field(default=None)

    # Audio info
    audio_url: str | None = Field(default=None)
    audio_duration: float | None = Field(default=None)

    # Results
    speakers: list[Speaker] | None = Field(
        default=None,
        description="Detected speakers",
    )
    segments: list[SpeakerSegment] | None = Field(
        default=None,
        description="Speaker segments",
    )
    overlaps: list[OverlapSegment] | None = Field(
        default=None,
        description="Overlap segments",
    )

    # Statistics
    stats: DiarizationStats | None = Field(
        default=None,
        description="Diarization statistics",
    )

    # RTTM output (if requested)
    rttm: str | None = Field(
        default=None,
        description="RTTM format output",
    )

    # Error
    error: str | None = Field(default=None)

    # Metadata
    metadata: dict[str, Any] | None = Field(default=None)


# =============================================================================
# Streaming Models (WebSocket/SSE)
# =============================================================================


class StreamingTranscriptChunk(StrictBaseModel):
    """A chunk of streaming transcription."""

    type: Literal["partial", "final"] = Field(
        ...,
        description="Chunk type (partial or final)",
    )
    text: str = Field(..., description="Transcribed text")
    start: float = Field(..., description="Start time")
    end: float = Field(..., description="End time")
    confidence: float = Field(default=1.0)
    words: list[TranscriptionWord] | None = Field(default=None)
    speaker: str | None = Field(default=None)
    is_final: bool = Field(default=False)


class StreamingSessionConfig(StrictBaseModel):
    """Configuration for streaming transcription session."""

    sample_rate: int = Field(
        default=16000,
        description="Audio sample rate in Hz",
    )
    encoding: Literal["pcm_s16le", "pcm_f32le", "opus", "flac"] = Field(
        default="pcm_s16le",
        description="Audio encoding",
    )
    channels: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Number of audio channels",
    )
    language_code: LanguageCode = Field(default=LanguageCode.FR)
    enable_diarization: bool = Field(default=False)
    interim_results: bool = Field(
        default=True,
        description="Return partial transcripts",
    )


class StreamingSessionStart(StrictBaseModel):
    """Message to start a streaming session."""

    type: Literal["session.start"] = Field(default="session.start")
    config: StreamingSessionConfig = Field(..., description="Session configuration")


class StreamingAudioChunk(StrictBaseModel):
    """Audio data chunk for streaming."""

    type: Literal["audio.chunk"] = Field(default="audio.chunk")
    audio: str = Field(..., description="Base64-encoded audio data")
    timestamp: float | None = Field(
        default=None,
        description="Timestamp of audio chunk",
    )


class StreamingSessionEnd(StrictBaseModel):
    """Message to end a streaming session."""

    type: Literal["session.end"] = Field(default="session.end")

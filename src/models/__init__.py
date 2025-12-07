"""Pydantic models for API request/response schemas."""

from src.models.common import (
    BaseAPIResponse,
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
)
from src.models.llm import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ModelInfo,
    ModelsResponse,
    StreamChoice,
    StreamDelta,
    ToolCall,
    ToolDefinition,
    Usage,
)
from src.models.stt import (
    DiarizationRequest,
    DiarizationResponse,
    Speaker,
    SpeakerSegment,
    TranscriptionJob,
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptionWord,
    Utterance,
)
from src.models.jobs import (
    JobCreate,
    JobResponse,
    JobStatus,
    JobType,
)

__all__ = [
    # Common
    "BaseAPIResponse",
    "ErrorResponse",
    "PaginatedResponse",
    "PaginationParams",
    # LLM
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "ModelInfo",
    "ModelsResponse",
    "StreamChoice",
    "StreamDelta",
    "ToolCall",
    "ToolDefinition",
    "Usage",
    # STT
    "DiarizationRequest",
    "DiarizationResponse",
    "Speaker",
    "SpeakerSegment",
    "TranscriptionJob",
    "TranscriptionRequest",
    "TranscriptionResponse",
    "TranscriptionWord",
    "Utterance",
    # Jobs
    "JobCreate",
    "JobResponse",
    "JobStatus",
    "JobType",
]

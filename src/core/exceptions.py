"""
Custom exceptions for Lexia API.

All exceptions inherit from LexiaAPIError and include proper HTTP status codes
and error details for consistent API error responses.
"""

from typing import Any


class LexiaAPIError(Exception):
    """Base exception for all Lexia API errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API response."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


# =============================================================================
# Authentication & Authorization Errors
# =============================================================================


class AuthenticationError(LexiaAPIError):
    """Raised when authentication fails."""

    status_code = 401
    error_code = "AUTHENTICATION_ERROR"
    message = "Authentication required"


class InvalidAPIKeyError(AuthenticationError):
    """Raised when API key is invalid."""

    error_code = "INVALID_API_KEY"
    message = "Invalid or expired API key"


class AuthorizationError(LexiaAPIError):
    """Raised when user lacks permission."""

    status_code = 403
    error_code = "AUTHORIZATION_ERROR"
    message = "You do not have permission to perform this action"


# =============================================================================
# Resource Errors
# =============================================================================


class NotFoundError(LexiaAPIError):
    """Raised when a resource is not found."""

    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


class JobNotFoundError(NotFoundError):
    """Raised when a job is not found."""

    error_code = "JOB_NOT_FOUND"
    message = "Job not found"

    def __init__(self, job_id: str) -> None:
        super().__init__(
            message=f"Job with ID '{job_id}' not found",
            details={"job_id": job_id},
        )


class ModelNotFoundError(NotFoundError):
    """Raised when a model is not found."""

    error_code = "MODEL_NOT_FOUND"
    message = "Model not found"

    def __init__(self, model_id: str) -> None:
        super().__init__(
            message=f"Model '{model_id}' not found or not available",
            details={"model_id": model_id},
        )


class TranscriptionNotFoundError(NotFoundError):
    """Raised when a transcription is not found."""

    error_code = "TRANSCRIPTION_NOT_FOUND"
    message = "Transcription not found"

    def __init__(self, transcription_id: str) -> None:
        super().__init__(
            message=f"Transcription with ID '{transcription_id}' not found",
            details={"transcription_id": transcription_id},
        )


# =============================================================================
# Validation Errors
# =============================================================================


class ValidationError(LexiaAPIError):
    """Raised when request validation fails."""

    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "Request validation failed"


class InvalidAudioFormatError(ValidationError):
    """Raised when audio format is not supported."""

    error_code = "INVALID_AUDIO_FORMAT"
    message = "Audio format not supported"

    def __init__(self, format_received: str, supported_formats: list[str]) -> None:
        super().__init__(
            message=f"Audio format '{format_received}' is not supported",
            details={
                "format_received": format_received,
                "supported_formats": supported_formats,
            },
        )


class FileTooLargeError(ValidationError):
    """Raised when uploaded file exceeds size limit."""

    error_code = "FILE_TOO_LARGE"
    message = "File size exceeds maximum allowed"

    def __init__(self, size_mb: float, max_size_mb: int) -> None:
        super().__init__(
            message=f"File size ({size_mb:.2f} MB) exceeds maximum ({max_size_mb} MB)",
            details={
                "file_size_mb": size_mb,
                "max_size_mb": max_size_mb,
            },
        )


class AudioTooLongError(ValidationError):
    """Raised when audio duration exceeds limit."""

    error_code = "AUDIO_TOO_LONG"
    message = "Audio duration exceeds maximum allowed"

    def __init__(self, duration_seconds: float, max_duration_seconds: int) -> None:
        super().__init__(
            message=f"Audio duration ({duration_seconds:.0f}s) exceeds maximum ({max_duration_seconds}s)",
            details={
                "duration_seconds": duration_seconds,
                "max_duration_seconds": max_duration_seconds,
            },
        )


# =============================================================================
# Rate Limiting Errors
# =============================================================================


class RateLimitError(LexiaAPIError):
    """Raised when rate limit is exceeded."""

    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Rate limit exceeded"

    def __init__(
        self,
        limit: int,
        remaining: int,
        reset_at: int,
    ) -> None:
        super().__init__(
            message="Rate limit exceeded. Please retry later.",
            details={
                "limit": limit,
                "remaining": remaining,
                "reset_at": reset_at,
            },
        )
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at


# =============================================================================
# Service Errors
# =============================================================================


class ServiceUnavailableError(LexiaAPIError):
    """Raised when an internal service is unavailable."""

    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


class LLMServiceError(ServiceUnavailableError):
    """Raised when LLM service fails."""

    error_code = "LLM_SERVICE_ERROR"
    message = "LLM service is unavailable"


class STTServiceError(ServiceUnavailableError):
    """Raised when STT service fails."""

    error_code = "STT_SERVICE_ERROR"
    message = "Speech-to-Text service is unavailable"


class DiarizationServiceError(ServiceUnavailableError):
    """Raised when Diarization service fails."""

    error_code = "DIARIZATION_SERVICE_ERROR"
    message = "Speaker Diarization service is unavailable"


# =============================================================================
# Storage Errors
# =============================================================================


class StorageError(LexiaAPIError):
    """Raised when storage operation fails."""

    status_code = 500
    error_code = "STORAGE_ERROR"
    message = "Storage operation failed"


class FileUploadError(StorageError):
    """Raised when file upload fails."""

    error_code = "FILE_UPLOAD_ERROR"
    message = "Failed to upload file"


class FileDownloadError(StorageError):
    """Raised when file download fails."""

    error_code = "FILE_DOWNLOAD_ERROR"
    message = "Failed to download file"


class FileNotFoundError(StorageError):
    """Raised when file is not found in storage."""

    status_code = 404
    error_code = "FILE_NOT_FOUND"
    message = "File not found in storage"


# =============================================================================
# Job Processing Errors
# =============================================================================


class JobError(LexiaAPIError):
    """Base class for job-related errors."""

    status_code = 500
    error_code = "JOB_ERROR"
    message = "Job processing error"


class JobAlreadyExistsError(JobError):
    """Raised when trying to create a duplicate job."""

    status_code = 409
    error_code = "JOB_ALREADY_EXISTS"
    message = "Job already exists"


class JobProcessingError(JobError):
    """Raised when job processing fails."""

    error_code = "JOB_PROCESSING_ERROR"
    message = "Job processing failed"

    def __init__(self, job_id: str, reason: str) -> None:
        super().__init__(
            message=f"Failed to process job '{job_id}': {reason}",
            details={"job_id": job_id, "reason": reason},
        )


class JobTimeoutError(JobError):
    """Raised when job processing times out."""

    status_code = 408
    error_code = "JOB_TIMEOUT"
    message = "Job processing timed out"

    def __init__(self, job_id: str, timeout_seconds: int) -> None:
        super().__init__(
            message=f"Job '{job_id}' timed out after {timeout_seconds} seconds",
            details={"job_id": job_id, "timeout_seconds": timeout_seconds},
        )

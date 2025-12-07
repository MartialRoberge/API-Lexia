"""
STT backend factory.

Creates the appropriate STT backend based on configuration.
"""

from src.core.config import Settings, get_settings
from src.services.stt.base import STTBackend

# Singleton instance
_stt_backend: STTBackend | None = None


def get_stt_backend(settings: Settings | None = None) -> STTBackend:
    """
    Get the configured STT backend.

    Args:
        settings: Application settings. Uses default if None.

    Returns:
        Configured STTBackend instance.
    """
    global _stt_backend

    if _stt_backend is not None:
        return _stt_backend

    if settings is None:
        settings = get_settings()

    if settings.use_mock_stt:
        from src.services.stt.mock_backend import MockSTTBackend

        _stt_backend = MockSTTBackend(
            default_language=settings.stt_default_language,
        )

    else:
        from src.services.stt.whisper_backend import WhisperBackend

        _stt_backend = WhisperBackend(
            service_url=settings.stt_service_url,
        )

    return _stt_backend


def reset_stt_backend() -> None:
    """Reset the STT backend singleton (for testing)."""
    global _stt_backend
    _stt_backend = None

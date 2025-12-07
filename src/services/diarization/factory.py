"""
Diarization backend factory.
"""

from src.core.config import Settings, get_settings
from src.services.diarization.base import DiarizationBackend

# Singleton instance
_diarization_backend: DiarizationBackend | None = None


def get_diarization_backend(settings: Settings | None = None) -> DiarizationBackend:
    """
    Get the configured diarization backend.

    Args:
        settings: Application settings. Uses default if None.

    Returns:
        Configured DiarizationBackend instance.
    """
    global _diarization_backend

    if _diarization_backend is not None:
        return _diarization_backend

    if settings is None:
        settings = get_settings()

    if settings.use_mock_diarization:
        from src.services.diarization.mock_backend import MockDiarizationBackend

        _diarization_backend = MockDiarizationBackend()

    else:
        from src.services.diarization.pyannote_backend import PyannoteBackend

        _diarization_backend = PyannoteBackend(
            service_url=settings.stt_service_url,  # Same service as STT
        )

    return _diarization_backend


def reset_diarization_backend() -> None:
    """Reset the diarization backend singleton (for testing)."""
    global _diarization_backend
    _diarization_backend = None

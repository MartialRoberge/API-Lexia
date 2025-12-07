"""STT service abstraction with Whisper backend."""

from src.services.stt.base import STTBackend
from src.services.stt.factory import get_stt_backend

__all__ = ["STTBackend", "get_stt_backend"]

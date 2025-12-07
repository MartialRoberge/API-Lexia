"""Diarization service abstraction with Pyannote backend."""

from src.services.diarization.base import DiarizationBackend
from src.services.diarization.factory import get_diarization_backend

__all__ = ["DiarizationBackend", "get_diarization_backend"]

"""
LLM backend factory.

Creates the appropriate LLM backend based on configuration.
"""

from src.core.config import Settings, get_settings
from src.services.llm.base import DEFAULT_MODEL_REGISTRY, LLMBackend

# Singleton instance
_llm_backend: LLMBackend | None = None


def get_llm_backend(settings: Settings | None = None) -> LLMBackend:
    """
    Get the configured LLM backend.

    Factory function that creates the appropriate LLM backend
    based on application settings. Uses singleton pattern for caching.

    Args:
        settings: Application settings. Uses default if None.

    Returns:
        Configured LLMBackend instance.
    """
    global _llm_backend

    if _llm_backend is not None:
        return _llm_backend

    if settings is None:
        settings = get_settings()

    if settings.use_mock_llm:
        from src.services.llm.mock_backend import MockLLMBackend

        _llm_backend = MockLLMBackend(registry=DEFAULT_MODEL_REGISTRY)

    else:
        from src.services.llm.vllm_backend import VLLMBackend

        _llm_backend = VLLMBackend(
            service_url=settings.llm_service_url,
            registry=DEFAULT_MODEL_REGISTRY,
        )

    return _llm_backend


def reset_llm_backend() -> None:
    """Reset the LLM backend singleton (for testing)."""
    global _llm_backend
    _llm_backend = None

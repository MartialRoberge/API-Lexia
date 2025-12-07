"""
Abstract base class for LLM backends.

Provides a consistent interface for LLM inference across different backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator

from src.models.llm import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelInfo,
)


@dataclass
class ModelConfig:
    """Configuration for a loaded model."""

    model_id: str
    display_name: str
    hf_model_name: str  # Hugging Face model path
    description: str = ""
    context_length: int = 4096
    capabilities: list[str] = field(default_factory=lambda: ["chat", "completion"])
    languages: list[str] = field(default_factory=lambda: ["en", "fr"])
    default_temperature: float = 0.7
    default_max_tokens: int = 2048
    supports_tools: bool = True
    supports_streaming: bool = True


class ModelRegistry:
    """
    Registry of available LLM models.

    Manages model configurations and provides lookup functionality.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}
        self._default_model: str | None = None

    def register(
        self,
        model: ModelConfig,
        is_default: bool = False,
    ) -> None:
        """Register a model configuration."""
        self._models[model.model_id] = model
        if is_default or self._default_model is None:
            self._default_model = model.model_id

    def get(self, model_id: str) -> ModelConfig | None:
        """Get model configuration by ID."""
        return self._models.get(model_id)

    def get_default(self) -> ModelConfig | None:
        """Get the default model configuration."""
        if self._default_model:
            return self._models.get(self._default_model)
        return None

    def list_models(self) -> list[ModelConfig]:
        """List all registered models."""
        return list(self._models.values())

    def to_model_info_list(self) -> list[ModelInfo]:
        """Convert registry to API ModelInfo list."""
        result: list[ModelInfo] = []
        for config in self._models.values():
            result.append(
                ModelInfo(
                    id=config.model_id,
                    created=int(datetime.now(timezone.utc).timestamp()),
                    owned_by="lexia",
                    display_name=config.display_name,
                    description=config.description,
                    context_length=config.context_length,
                    capabilities=config.capabilities,
                    languages=config.languages,
                )
            )
        return result


# Default model registry with pre-configured models
DEFAULT_MODEL_REGISTRY = ModelRegistry()

# Register the main Lexia model
DEFAULT_MODEL_REGISTRY.register(
    ModelConfig(
        model_id="general7Bv2",
        display_name="General 7B v2",
        hf_model_name="Marsouuu/general7Bv2-ECE-PRYMMAL-Martial",
        description="General-purpose 7B model fine-tuned for French and English. "
        "Based on Qwen2 architecture with SLERP merge.",
        context_length=4096,
        capabilities=["chat", "completion", "tool_calls"],
        languages=["fr", "en"],
        default_temperature=0.7,
        default_max_tokens=2048,
        supports_tools=True,
        supports_streaming=True,
    ),
    is_default=True,
)


class LLMBackend(ABC):
    """Abstract base class for LLM inference backends."""

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or DEFAULT_MODEL_REGISTRY

    @abstractmethod
    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """
        Generate a chat completion.

        Args:
            request: Chat completion request with messages and parameters.

        Returns:
            ChatCompletionResponse with generated content.

        Raises:
            ModelNotFoundError: If the requested model is not available.
            LLMServiceError: If generation fails.
        """
        ...

    @abstractmethod
    async def stream_generate(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """
        Generate a chat completion with streaming.

        Args:
            request: Chat completion request with messages and parameters.

        Yields:
            ChatCompletionChunk objects as content is generated.
        """
        ...

    @abstractmethod
    async def get_models(self) -> list[ModelInfo]:
        """
        Get list of available models.

        Returns:
            List of ModelInfo objects.
        """
        ...

    @abstractmethod
    async def get_model(self, model_id: str) -> ModelInfo | None:
        """
        Get information about a specific model.

        Args:
            model_id: Model identifier.

        Returns:
            ModelInfo if found, None otherwise.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the LLM backend is healthy.

        Returns:
            True if backend is operational.
        """
        ...

    def resolve_model_id(self, model_id: str) -> str:
        """
        Resolve a model ID, handling defaults and aliases.

        Args:
            model_id: Requested model ID.

        Returns:
            Resolved model ID.
        """
        # Check if model exists in registry
        if self.registry.get(model_id):
            return model_id

        # Try to find by HF name
        for config in self.registry.list_models():
            if config.hf_model_name == model_id:
                return config.model_id

        # Return as-is if not found (will error in generate)
        return model_id

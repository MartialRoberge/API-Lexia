"""
Mock LLM backend for development and testing.

Provides simulated responses without requiring a GPU or vLLM server.
"""

import asyncio
import time
import uuid
from typing import AsyncIterator

from src.core.logging import get_logger
from src.models.llm import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    MessageRole,
    ModelInfo,
    StreamChoice,
    StreamDelta,
    Usage,
)
from src.services.llm.base import LLMBackend, ModelRegistry

logger = get_logger(__name__)


# Sample responses for mock mode
MOCK_RESPONSES = [
    "Je suis un assistant IA. Comment puis-je vous aider aujourd'hui ?",
    "C'est une question intéressante. Laissez-moi y réfléchir...",
    "D'après mon analyse, voici ce que je peux vous dire :",
    "Bien sûr, je peux vous aider avec cela. Voici ma réponse :",
    "Merci pour votre question. Voici les informations demandées :",
]


class MockLLMBackend(LLMBackend):
    """
    Mock LLM backend for development.

    Generates simulated responses without an actual LLM.
    Useful for testing API integration without GPU resources.
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        response_delay: float = 0.1,
        stream_delay: float = 0.02,
    ) -> None:
        """
        Initialize mock backend.

        Args:
            registry: Model registry. Uses default if None.
            response_delay: Delay before returning response (seconds).
            stream_delay: Delay between stream chunks (seconds).
        """
        super().__init__(registry)
        self.response_delay = response_delay
        self.stream_delay = stream_delay
        self._request_count = 0

    def _generate_mock_response(self, request: ChatCompletionRequest) -> str:
        """Generate a mock response based on the request."""
        # Get the last user message
        last_user_message = ""
        for msg in reversed(request.messages):
            if msg.role == MessageRole.USER and msg.content:
                last_user_message = msg.content
                break

        # Generate response based on message content
        self._request_count += 1
        base_response = MOCK_RESPONSES[self._request_count % len(MOCK_RESPONSES)]

        if last_user_message:
            # Echo back part of the question
            response = f"{base_response}\n\nVous avez demandé: '{last_user_message[:50]}...'\n\n"
            response += "Ceci est une réponse simulée en mode développement. "
            response += "En production, vous recevriez une vraie réponse du modèle LLM."
        else:
            response = base_response

        return response

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Rough estimate: ~4 characters per token for French
        return len(text) // 4

    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """Generate mock chat completion."""
        logger.info(
            "mock_llm_generate",
            model=request.model,
            messages_count=len(request.messages),
        )

        # Simulate processing time
        await asyncio.sleep(self.response_delay)

        # Generate response
        response_text = self._generate_mock_response(request)

        # Calculate tokens
        prompt_tokens = sum(
            self._estimate_tokens(m.content or "") for m in request.messages
        )
        completion_tokens = self._estimate_tokens(response_text)

        # Limit response if max_tokens specified
        if request.max_tokens:
            max_chars = request.max_tokens * 4
            if len(response_text) > max_chars:
                response_text = response_text[:max_chars] + "..."
                completion_tokens = request.max_tokens

        return ChatCompletionResponse(
            id=f"chatcmpl-mock-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(
                        role=MessageRole.ASSISTANT,
                        content=response_text,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            system_fingerprint="mock-backend-v1",
        )

    async def stream_generate(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Generate mock streaming chat completion."""
        logger.info(
            "mock_llm_stream_generate",
            model=request.model,
            messages_count=len(request.messages),
        )

        completion_id = f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        # Generate full response
        response_text = self._generate_mock_response(request)

        # Limit response if max_tokens specified
        if request.max_tokens:
            max_chars = request.max_tokens * 4
            response_text = response_text[:max_chars]

        # Split into words for streaming
        words = response_text.split()

        # First chunk with role
        yield ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[
                StreamChoice(
                    index=0,
                    delta=StreamDelta(role=MessageRole.ASSISTANT),
                    finish_reason=None,
                )
            ],
        )

        # Stream words
        prompt_tokens = sum(
            self._estimate_tokens(m.content or "") for m in request.messages
        )
        completion_tokens = 0

        for i, word in enumerate(words):
            await asyncio.sleep(self.stream_delay)

            # Add space before word (except first)
            content = f" {word}" if i > 0 else word
            completion_tokens += self._estimate_tokens(content)

            yield ChatCompletionChunk(
                id=completion_id,
                created=created,
                model=request.model,
                choices=[
                    StreamChoice(
                        index=0,
                        delta=StreamDelta(content=content),
                        finish_reason=None,
                    )
                ],
            )

        # Final chunk with finish reason and usage
        yield ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[
                StreamChoice(
                    index=0,
                    delta=StreamDelta(),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def get_models(self) -> list[ModelInfo]:
        """Get available models (from registry)."""
        models = self.registry.to_model_info_list()
        for model in models:
            model.status = "available"
        return models

    async def get_model(self, model_id: str) -> ModelInfo | None:
        """Get specific model info."""
        models = await self.get_models()
        for model in models:
            if model.id == model_id:
                return model
        return None

    async def health_check(self) -> bool:
        """Mock backend is always healthy."""
        return True

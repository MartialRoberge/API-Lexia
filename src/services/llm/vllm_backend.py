"""
vLLM backend for LLM inference.

Connects to a vLLM server running as a separate service.
Uses the OpenAI-compatible API provided by vLLM.
"""

import time
import uuid
from typing import Any, AsyncIterator

import httpx

from src.core.exceptions import LLMServiceError, ModelNotFoundError
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


class VLLMBackend(LLMBackend):
    """
    vLLM inference backend.

    Connects to a vLLM server and uses its OpenAI-compatible API.
    """

    def __init__(
        self,
        service_url: str,
        registry: ModelRegistry | None = None,
        timeout: float = 120.0,
    ) -> None:
        """
        Initialize vLLM backend.

        Args:
            service_url: URL of the vLLM server (e.g., http://llm:8001).
            registry: Model registry. Uses default if None.
            timeout: Request timeout in seconds.
        """
        super().__init__(registry)
        self.service_url = service_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.service_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _build_request_payload(
        self,
        request: ChatCompletionRequest,
    ) -> dict[str, Any]:
        """Build request payload for vLLM API."""
        # Resolve model to HF name
        model_config = self.registry.get(request.model)
        if model_config:
            model_name = model_config.hf_model_name
        else:
            model_name = request.model

        # Build messages
        messages = []
        for msg in request.messages:
            # Handle both Enum and string role values
            role = msg.role.value if hasattr(msg.role, 'value') else msg.role
            message_dict: dict[str, Any] = {
                "role": role,
            }
            if msg.content is not None:
                message_dict["content"] = msg.content
            if msg.name:
                message_dict["name"] = msg.name
            if msg.tool_calls:
                message_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type.value,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                message_dict["tool_call_id"] = msg.tool_call_id
            messages.append(message_dict)

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "n": request.n,
            "stream": request.stream,
        }

        # Optional parameters
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop is not None:
            payload["stop"] = request.stop
        if request.frequency_penalty != 0:
            payload["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty != 0:
            payload["presence_penalty"] = request.presence_penalty
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.tools:
            payload["tools"] = [
                {
                    "type": t.type.value,
                    "function": {
                        "name": t.function.name,
                        "description": t.function.description,
                        "parameters": t.function.parameters,
                    },
                }
                for t in request.tools
            ]
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice
        if request.response_format:
            payload["response_format"] = {
                "type": request.response_format.type,
            }
            if request.response_format.json_schema:
                payload["response_format"]["json_schema"] = (
                    request.response_format.json_schema
                )

        return payload

    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """Generate chat completion via vLLM."""
        # Validate model
        model_id = self.resolve_model_id(request.model)

        try:
            client = await self._get_client()
            payload = self._build_request_payload(request)
            payload["stream"] = False

            logger.debug(
                "vllm_request",
                model=model_id,
                messages_count=len(request.messages),
            )

            response = await client.post(
                "/v1/chat/completions",
                json=payload,
            )

            if response.status_code == 404:
                raise ModelNotFoundError(model_id)

            response.raise_for_status()
            data = response.json()

            # Parse response
            choices = []
            for choice_data in data.get("choices", []):
                message = choice_data.get("message", {})
                choices.append(
                    Choice(
                        index=choice_data.get("index", 0),
                        message=ChoiceMessage(
                            role=MessageRole(message.get("role", "assistant")),
                            content=message.get("content"),
                            tool_calls=None,  # Parse if present
                        ),
                        finish_reason=choice_data.get("finish_reason"),
                    )
                )

            usage_data = data.get("usage", {})
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

            return ChatCompletionResponse(
                id=data.get("id", f"chatcmpl-{uuid.uuid4().hex[:12]}"),
                created=data.get("created", int(time.time())),
                model=model_id,
                choices=choices,
                usage=usage,
                system_fingerprint=data.get("system_fingerprint"),
            )

        except httpx.HTTPStatusError as e:
            logger.error("vllm_http_error", status=e.response.status_code)
            raise LLMServiceError(
                message=f"vLLM request failed: {e.response.text}",
                details={"status_code": e.response.status_code},
            ) from e
        except httpx.RequestError as e:
            logger.error("vllm_request_error", error=str(e))
            raise LLMServiceError(
                message=f"Failed to connect to vLLM: {e}",
            ) from e

    async def stream_generate(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Generate chat completion with streaming via vLLM."""
        model_id = self.resolve_model_id(request.model)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        try:
            client = await self._get_client()
            payload = self._build_request_payload(request)
            payload["stream"] = True

            logger.debug(
                "vllm_stream_request",
                model=model_id,
                messages_count=len(request.messages),
            )

            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json=payload,
            ) as response:
                if response.status_code == 404:
                    raise ModelNotFoundError(model_id)
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            import json

                            data = json.loads(data_str)
                            choices = []

                            for choice_data in data.get("choices", []):
                                delta = choice_data.get("delta", {})
                                choices.append(
                                    StreamChoice(
                                        index=choice_data.get("index", 0),
                                        delta=StreamDelta(
                                            role=MessageRole(delta["role"])
                                            if "role" in delta
                                            else None,
                                            content=delta.get("content"),
                                            tool_calls=None,
                                        ),
                                        finish_reason=choice_data.get("finish_reason"),
                                    )
                                )

                            # Parse usage if present (final chunk)
                            usage = None
                            if "usage" in data:
                                usage_data = data["usage"]
                                usage = Usage(
                                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                                    completion_tokens=usage_data.get(
                                        "completion_tokens", 0
                                    ),
                                    total_tokens=usage_data.get("total_tokens", 0),
                                )

                            yield ChatCompletionChunk(
                                id=completion_id,
                                created=created,
                                model=model_id,
                                choices=choices,
                                usage=usage,
                            )

                        except Exception as e:
                            logger.warning(
                                "vllm_stream_parse_error",
                                error=str(e),
                                line=data_str[:100],
                            )
                            continue

        except httpx.HTTPStatusError as e:
            logger.error("vllm_stream_http_error", status=e.response.status_code)
            raise LLMServiceError(
                message=f"vLLM streaming failed: {e.response.text}",
            ) from e
        except httpx.RequestError as e:
            logger.error("vllm_stream_request_error", error=str(e))
            raise LLMServiceError(
                message=f"Failed to connect to vLLM: {e}",
            ) from e

    async def get_models(self) -> list[ModelInfo]:
        """Get available models."""
        # Return registered models with their status
        models = self.registry.to_model_info_list()

        # Try to check vLLM for loaded models
        try:
            client = await self._get_client()
            response = await client.get("/v1/models")
            if response.status_code == 200:
                data = response.json()
                loaded_models = {m["id"] for m in data.get("data", [])}

                # Update status based on what's loaded
                for model in models:
                    config = self.registry.get(model.id)
                    if config and config.hf_model_name in loaded_models:
                        model.status = "available"
                    else:
                        model.status = "loading"
        except Exception:
            # If we can't reach vLLM, mark models as unavailable
            for model in models:
                model.status = "unavailable"

        return models

    async def get_model(self, model_id: str) -> ModelInfo | None:
        """Get specific model info."""
        models = await self.get_models()
        for model in models:
            if model.id == model_id:
                return model
        return None

    async def health_check(self) -> bool:
        """Check if vLLM server is healthy."""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

"""
LLM API router.

Provides chat completion endpoints compatible with OpenAI/Mistral format.
"""

import json
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from src.core.auth import CurrentUser
from src.core.config import Settings, get_settings
from src.core.exceptions import ModelNotFoundError
from src.core.rate_limit import RateLimitedUser
from src.models.llm import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelInfo,
    ModelsResponse,
)
from src.services.llm.factory import get_llm_backend

router = APIRouter(prefix="/v1", tags=["LLM"])


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="List available models",
    description="Returns a list of available LLM models.",
)
async def list_models(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelsResponse:
    """
    List available models.

    Returns all LLM models available for inference.
    """
    backend = get_llm_backend(settings)
    models = await backend.get_models()
    return ModelsResponse(data=models)


@router.get(
    "/models/{model_id}",
    response_model=ModelInfo,
    summary="Get model info",
    description="Returns information about a specific model.",
)
async def get_model(
    model_id: str,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelInfo:
    """
    Get model information.

    Args:
        model_id: The model identifier.
    """
    backend = get_llm_backend(settings)
    model = await backend.get_model(model_id)
    if model is None:
        raise ModelNotFoundError(model_id)
    return model


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="Create chat completion",
    description="Generate a chat completion response.",
)
async def create_chat_completion(
    request: ChatCompletionRequest,
    user: RateLimitedUser,
    settings: Annotated[Settings, Depends(get_settings)],
    http_request: Request,
) -> ChatCompletionResponse | StreamingResponse:
    """
    Create a chat completion.

    Generate a response based on the conversation history.
    Supports both regular and streaming responses.
    """
    backend = get_llm_backend(settings)

    if request.stream:
        # Return streaming response
        async def generate():
            async for chunk in backend.stream_generate(request):
                data = chunk.model_dump_json()
                yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Regular response
    response = await backend.generate(request)
    return response


@router.post(
    "/completions",
    response_model=ChatCompletionResponse,
    summary="Create completion (legacy)",
    description="Legacy completion endpoint - converts to chat format.",
    deprecated=True,
)
async def create_completion(
    request: ChatCompletionRequest,
    user: RateLimitedUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatCompletionResponse:
    """
    Create a completion (legacy endpoint).

    This endpoint is deprecated. Use /v1/chat/completions instead.
    """
    backend = get_llm_backend(settings)
    return await backend.generate(request)

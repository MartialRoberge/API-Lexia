"""
Pydantic models for LLM (Large Language Model) API endpoints.

Inspired by OpenAI/Mistral API format for compatibility with LiteLLM.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator

from src.models.common import StrictBaseModel


class MessageRole(str, Enum):
    """Roles for chat messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolType(str, Enum):
    """Types of tools available."""

    FUNCTION = "function"


class FunctionDefinition(StrictBaseModel):
    """Definition of a callable function."""

    name: str = Field(..., min_length=1, max_length=64, description="Function name")
    description: str | None = Field(
        default=None,
        max_length=1024,
        description="Function description",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for function parameters",
    )


class ToolDefinition(StrictBaseModel):
    """Definition of a tool that can be called by the model."""

    type: ToolType = Field(default=ToolType.FUNCTION, description="Tool type")
    function: FunctionDefinition = Field(..., description="Function definition")


class FunctionCall(StrictBaseModel):
    """A function call made by the model."""

    name: str = Field(..., description="Name of the function to call")
    arguments: str = Field(..., description="JSON string of function arguments")


class ToolCall(StrictBaseModel):
    """A tool call made by the model."""

    id: str = Field(..., description="Unique ID for this tool call")
    type: ToolType = Field(default=ToolType.FUNCTION, description="Tool type")
    function: FunctionCall = Field(..., description="Function call details")


class ChatMessage(StrictBaseModel):
    """A message in the chat conversation."""

    role: MessageRole = Field(..., description="Role of the message sender")
    content: str | None = Field(
        default=None,
        description="Message content (null for tool calls)",
    )
    name: str | None = Field(
        default=None,
        max_length=64,
        description="Name of the sender (for multi-user chats)",
    )
    tool_calls: list[ToolCall] | None = Field(
        default=None,
        description="Tool calls made by assistant",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="ID of tool call this message responds to",
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None, info: Any) -> str | None:
        """Validate that user/system messages have content."""
        # Note: info.data contains already validated fields
        return v


class ResponseFormat(StrictBaseModel):
    """Response format specification."""

    type: Literal["text", "json_object", "json_schema"] = Field(
        default="text",
        description="Response format type",
    )
    json_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON schema for json_schema type",
    )


class ChatCompletionRequest(StrictBaseModel):
    """
    Request for chat completion.

    Compatible with OpenAI/Mistral API format.
    """

    model: str = Field(
        ...,
        min_length=1,
        description="Model identifier to use",
        examples=["general7Bv2"],
    )
    messages: list[ChatMessage] = Field(
        ...,
        min_length=1,
        description="List of messages in the conversation",
    )

    # Generation parameters
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0-2)",
    )
    top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling probability",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=32768,
        description="Maximum tokens to generate",
    )
    min_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Minimum tokens to generate",
    )
    stop: str | list[str] | None = Field(
        default=None,
        description="Stop sequences",
    )

    # Advanced parameters
    frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty (-2 to 2)",
    )
    presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty (-2 to 2)",
    )
    n: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of completions to generate",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for reproducibility",
    )

    # Streaming
    stream: bool = Field(
        default=False,
        description="Enable streaming responses",
    )

    # Tools
    tools: list[ToolDefinition] | None = Field(
        default=None,
        description="Available tools for function calling",
    )
    tool_choice: Literal["auto", "none", "required"] | dict[str, Any] | None = Field(
        default=None,
        description="Tool calling behavior",
    )
    parallel_tool_calls: bool = Field(
        default=True,
        description="Allow parallel tool calls",
    )

    # Response format
    response_format: ResponseFormat | None = Field(
        default=None,
        description="Response format specification",
    )

    # User tracking
    user: str | None = Field(
        default=None,
        max_length=256,
        description="Unique user identifier for tracking",
    )


class Usage(StrictBaseModel):
    """Token usage statistics."""

    prompt_tokens: int = Field(..., description="Tokens in the prompt")
    completion_tokens: int = Field(..., description="Tokens in the completion")
    total_tokens: int = Field(..., description="Total tokens used")


class ChoiceMessage(StrictBaseModel):
    """Message in a completion choice."""

    role: MessageRole = Field(default=MessageRole.ASSISTANT)
    content: str | None = Field(default=None, description="Generated content")
    tool_calls: list[ToolCall] | None = Field(
        default=None,
        description="Tool calls made",
    )


class Choice(StrictBaseModel):
    """A completion choice."""

    index: int = Field(..., description="Choice index")
    message: ChoiceMessage = Field(..., description="Generated message")
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = Field(
        default=None,
        description="Reason generation stopped",
    )
    logprobs: dict[str, Any] | None = Field(
        default=None,
        description="Log probabilities (if requested)",
    )


class ChatCompletionResponse(StrictBaseModel):
    """
    Response from chat completion.

    Compatible with OpenAI/Mistral API format.
    """

    id: str = Field(..., description="Unique completion ID")
    object: Literal["chat.completion"] = Field(
        default="chat.completion",
        description="Object type",
    )
    created: int = Field(..., description="Unix timestamp of creation")
    model: str = Field(..., description="Model used for completion")
    choices: list[Choice] = Field(..., description="Generated completions")
    usage: Usage = Field(..., description="Token usage statistics")
    system_fingerprint: str | None = Field(
        default=None,
        description="System fingerprint for reproducibility",
    )


# =============================================================================
# Streaming Models
# =============================================================================


class StreamDelta(StrictBaseModel):
    """Delta content in a streaming response."""

    role: MessageRole | None = Field(default=None)
    content: str | None = Field(default=None)
    tool_calls: list[ToolCall] | None = Field(default=None)


class StreamChoice(StrictBaseModel):
    """A choice in a streaming response."""

    index: int = Field(..., description="Choice index")
    delta: StreamDelta = Field(..., description="Delta content")
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = Field(
        default=None
    )
    logprobs: dict[str, Any] | None = Field(default=None)


class ChatCompletionChunk(StrictBaseModel):
    """A chunk in a streaming chat completion response."""

    id: str = Field(..., description="Completion ID")
    object: Literal["chat.completion.chunk"] = Field(default="chat.completion.chunk")
    created: int = Field(..., description="Unix timestamp")
    model: str = Field(..., description="Model used")
    choices: list[StreamChoice] = Field(..., description="Stream choices")
    system_fingerprint: str | None = Field(default=None)
    usage: Usage | None = Field(
        default=None,
        description="Usage (only in final chunk)",
    )


# =============================================================================
# Model Information
# =============================================================================


class ModelInfo(StrictBaseModel):
    """Information about an available model."""

    id: str = Field(..., description="Model identifier")
    object: Literal["model"] = Field(default="model")
    created: int = Field(..., description="Unix timestamp of model creation")
    owned_by: str = Field(default="lexia", description="Model owner")

    # Extended info
    display_name: str | None = Field(default=None, description="Human-readable name")
    description: str | None = Field(default=None, description="Model description")
    context_length: int = Field(default=4096, description="Maximum context length")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Model capabilities (chat, completion, etc.)",
    )
    languages: list[str] = Field(
        default_factory=list,
        description="Supported languages",
    )

    # Status
    status: Literal["available", "loading", "unavailable"] = Field(
        default="available",
        description="Model availability status",
    )


class ModelsResponse(StrictBaseModel):
    """Response listing available models."""

    object: Literal["list"] = Field(default="list")
    data: list[ModelInfo] = Field(..., description="Available models")

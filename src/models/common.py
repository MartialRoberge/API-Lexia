"""
Common Pydantic models shared across the API.

These models provide consistent base structures for all API responses.
"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# Type variable for generic responses
T = TypeVar("T")


class StrictBaseModel(BaseModel):
    """Base model with strict configuration for all API schemas."""

    model_config = ConfigDict(
        # Strict mode: no extra fields allowed
        extra="forbid",
        # Use enum values instead of names
        use_enum_values=True,
        # Validate default values
        validate_default=True,
        # Validate on assignment
        validate_assignment=True,
        # Serialize by alias
        populate_by_name=True,
        # Strip whitespace from strings
        str_strip_whitespace=True,
    )


class BaseAPIResponse(StrictBaseModel, Generic[T]):
    """
    Base response wrapper for all API responses.

    Provides consistent structure with data, metadata, and optional error info.
    """

    success: bool = Field(default=True, description="Whether the request was successful")
    data: T = Field(..., description="Response data")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp (UTC)",
    )


class ErrorDetail(StrictBaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional error details",
    )
    path: str | None = Field(
        default=None,
        description="Request path that caused the error",
    )
    request_id: str | None = Field(
        default=None,
        description="Request ID for tracking",
    )


class ErrorResponse(StrictBaseModel):
    """
    Standard error response format.

    Follows RFC 7807 Problem Details pattern.
    """

    success: bool = Field(default=False)
    error: ErrorDetail = Field(..., description="Error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginationParams(StrictBaseModel):
    """Pagination parameters for list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page",
    )
    offset: int = Field(default=0, ge=0, description="Offset for pagination")

    @property
    def skip(self) -> int:
        """Calculate skip value for database queries."""
        return (self.page - 1) * self.limit


class PageDetails(StrictBaseModel):
    """Pagination details in response."""

    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")
    next_url: str | None = Field(default=None, description="URL for next page")
    prev_url: str | None = Field(default=None, description="URL for previous page")


class PaginatedResponse(StrictBaseModel, Generic[T]):
    """Paginated response for list endpoints."""

    success: bool = Field(default=True)
    data: list[T] = Field(..., description="List of items")
    page_details: PageDetails = Field(..., description="Pagination details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        limit: int,
        base_url: str | None = None,
    ) -> "PaginatedResponse[T]":
        """Create a paginated response with calculated page details."""
        total_pages = (total + limit - 1) // limit if limit > 0 else 0
        has_next = page < total_pages
        has_prev = page > 1

        next_url = None
        prev_url = None
        if base_url:
            if has_next:
                next_url = f"{base_url}?page={page + 1}&limit={limit}"
            if has_prev:
                prev_url = f"{base_url}?page={page - 1}&limit={limit}"

        return cls(
            data=items,
            page_details=PageDetails(
                total=total,
                page=page,
                limit=limit,
                total_pages=total_pages,
                has_next=has_next,
                has_prev=has_prev,
                next_url=next_url,
                prev_url=prev_url,
            ),
        )


class HealthResponse(StrictBaseModel):
    """Health check response."""

    status: str = Field(default="healthy", description="Service status")
    version: str = Field(..., description="API version")
    services: dict[str, str] = Field(
        default_factory=dict,
        description="Status of dependent services",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class UsageStats(StrictBaseModel):
    """Usage statistics for billing/monitoring."""

    total_requests: int = Field(default=0, description="Total API requests")
    total_tokens: int = Field(default=0, description="Total tokens processed")
    total_audio_seconds: float = Field(
        default=0.0,
        description="Total audio duration processed (seconds)",
    )
    period_start: datetime = Field(..., description="Start of usage period")
    period_end: datetime = Field(..., description="End of usage period")

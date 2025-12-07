"""
Rate limiting implementation using Redis.

Implements a sliding window rate limiter with burst allowance.
"""

import time
from typing import Annotated

from fastapi import Depends, Request, Response

from src.core.auth import AuthenticatedUser, get_current_user
from src.core.config import Settings, get_settings
from src.core.exceptions import RateLimitError


class RateLimiter:
    """
    Sliding window rate limiter with Redis backend.

    Uses a sorted set in Redis to track request timestamps per API key.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.rate_limit_enabled
        self.default_limit = settings.rate_limit_requests_per_minute
        self.burst = settings.rate_limit_burst
        self.window_seconds = 60

    async def check_rate_limit(
        self,
        key: str,
        limit: int | None = None,
        redis_client: object | None = None,
    ) -> tuple[int, int, int]:
        """
        Check if a request is within rate limits.

        Args:
            key: Unique identifier for rate limiting (usually API key ID).
            limit: Custom limit for this key. Uses default if None.
            redis_client: Redis client instance.

        Returns:
            Tuple of (limit, remaining, reset_timestamp).

        Raises:
            RateLimitError: If rate limit is exceeded.
        """
        if not self.enabled:
            return (self.default_limit, self.default_limit, 0)

        if redis_client is None:
            # No Redis available, skip rate limiting
            return (self.default_limit, self.default_limit, 0)

        effective_limit = limit or self.default_limit
        now = time.time()
        window_start = now - self.window_seconds
        redis_key = f"ratelimit:{key}"

        # Use Redis pipeline for atomic operations
        pipe = redis_client.pipeline()

        # Remove expired entries
        pipe.zremrangebyscore(redis_key, 0, window_start)

        # Count current requests in window
        pipe.zcard(redis_key)

        # Add current request
        pipe.zadd(redis_key, {str(now): now})

        # Set expiry on the key
        pipe.expire(redis_key, self.window_seconds + 10)

        results = await pipe.execute()
        current_count = results[1]

        # Calculate remaining (including burst allowance)
        total_limit = effective_limit + self.burst
        remaining = max(0, total_limit - current_count - 1)
        reset_at = int(now + self.window_seconds)

        if current_count >= total_limit:
            raise RateLimitError(
                limit=effective_limit,
                remaining=0,
                reset_at=reset_at,
            )

        return (effective_limit, remaining, reset_at)

    def add_rate_limit_headers(
        self,
        response: Response,
        limit: int,
        remaining: int,
        reset_at: int,
    ) -> None:
        """Add rate limit headers to response."""
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter(
    settings: Annotated[Settings, Depends(get_settings)]
) -> RateLimiter:
    """Get or create rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(settings)
    return _rate_limiter


async def check_rate_limit(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> AuthenticatedUser:
    """
    Dependency that checks rate limits for authenticated requests.

    This should be used after authentication to apply rate limiting.

    Args:
        request: FastAPI request object.
        response: FastAPI response object.
        user: Authenticated user from API key.
        rate_limiter: Rate limiter instance.

    Returns:
        The authenticated user if within rate limits.

    Raises:
        RateLimitError: If rate limit is exceeded.
    """
    # Get Redis client from request state
    redis_client = getattr(request.state, "redis", None)

    # Check rate limit using user's API key ID
    limit, remaining, reset_at = await rate_limiter.check_rate_limit(
        key=user.api_key_id,
        limit=user.rate_limit,
        redis_client=redis_client,
    )

    # Add rate limit headers to response
    rate_limiter.add_rate_limit_headers(response, limit, remaining, reset_at)

    return user


# Type alias for dependency injection
RateLimitedUser = Annotated[AuthenticatedUser, Depends(check_rate_limit)]

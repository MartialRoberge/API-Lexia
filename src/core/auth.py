"""
Authentication and authorization utilities.

Provides API key validation, generation, and request authentication.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import APIKeyHeader

from src.core.config import Settings, get_settings
from src.core.exceptions import AuthenticationError, InvalidAPIKeyError


# API Key header scheme
api_key_header = APIKeyHeader(
    name="Authorization",
    scheme_name="Bearer",
    description="API Key authentication. Format: 'Bearer lx_your_api_key'",
    auto_error=False,
)


class APIKeyManager:
    """Manages API key generation, hashing, and validation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._salt = settings.api_key_salt.encode()
        self._prefix = settings.api_key_prefix

    def generate_api_key(self) -> str:
        """
        Generate a new API key.

        Returns:
            A new API key with the configured prefix (e.g., 'lx_abc123...').
        """
        # Generate 32 random bytes (256 bits of entropy)
        random_bytes = secrets.token_bytes(32)
        # Convert to URL-safe base64, remove padding
        key_body = secrets.token_urlsafe(32)
        return f"{self._prefix}{key_body}"

    def hash_api_key(self, api_key: str) -> str:
        """
        Hash an API key for secure storage.

        Args:
            api_key: The plain-text API key.

        Returns:
            The hashed API key.
        """
        # Remove prefix if present
        key_body = api_key
        if key_body.startswith(self._prefix):
            key_body = key_body[len(self._prefix) :]

        # Use SHA-256 with salt for hashing
        return hashlib.sha256(self._salt + key_body.encode()).hexdigest()

    def verify_api_key(self, api_key: str, hashed_key: str) -> bool:
        """
        Verify an API key against its hash.

        Args:
            api_key: The plain-text API key to verify.
            hashed_key: The stored hash to compare against.

        Returns:
            True if the key matches, False otherwise.
        """
        computed_hash = self.hash_api_key(api_key)
        return secrets.compare_digest(computed_hash, hashed_key)

    def extract_key_from_header(self, authorization: str | None) -> str:
        """
        Extract API key from Authorization header.

        Args:
            authorization: The Authorization header value.

        Returns:
            The extracted API key.

        Raises:
            AuthenticationError: If header is missing or malformed.
        """
        if not authorization:
            raise AuthenticationError(
                message="Missing Authorization header",
                details={"header": "Authorization"},
            )

        # Support both "Bearer <key>" and just "<key>"
        parts = authorization.split()

        if len(parts) == 1:
            return parts[0]
        elif len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        else:
            raise AuthenticationError(
                message="Invalid Authorization header format",
                details={"expected": "Bearer <api_key> or <api_key>"},
            )


class AuthenticatedUser:
    """Represents an authenticated API user."""

    def __init__(
        self,
        user_id: str,
        api_key_id: str,
        organization_id: str | None = None,
        rate_limit: int = 60,
        permissions: list[str] | None = None,
    ) -> None:
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.organization_id = organization_id
        self.rate_limit = rate_limit
        self.permissions = permissions or []
        self.authenticated_at = datetime.now(timezone.utc)

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions or "*" in self.permissions


# Global API key manager instance (initialized lazily)
_api_key_manager: APIKeyManager | None = None


def get_api_key_manager(
    settings: Annotated[Settings, Depends(get_settings)]
) -> APIKeyManager:
    """Get or create API key manager instance."""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager(settings)
    return _api_key_manager


async def validate_api_key(
    authorization: Annotated[str | None, Header()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> str:
    """
    Validate API key from Authorization header.

    This is a simplified validation that extracts and validates the key format.
    Full validation against the database is done in get_current_user.

    Args:
        authorization: The Authorization header value.
        settings: Application settings.

    Returns:
        The validated API key.

    Raises:
        AuthenticationError: If the key is missing or invalid.
    """
    if settings is None:
        settings = get_settings()

    manager = APIKeyManager(settings)
    api_key = manager.extract_key_from_header(authorization)

    # Validate key format
    if not api_key.startswith(settings.api_key_prefix):
        raise InvalidAPIKeyError(
            details={"reason": f"API key must start with '{settings.api_key_prefix}'"}
        )

    # Validate minimum length
    if len(api_key) < 20:
        raise InvalidAPIKeyError(details={"reason": "API key is too short"})

    return api_key


async def get_current_user(
    request: Request,
    api_key: Annotated[str, Depends(validate_api_key)],
) -> AuthenticatedUser:
    """
    Get the current authenticated user from the API key.

    This dependency should be used on protected routes. It validates the API key
    against the database and returns the authenticated user.

    Args:
        request: The FastAPI request object.
        api_key: The validated API key.

    Returns:
        The authenticated user.

    Raises:
        InvalidAPIKeyError: If the API key is not found or revoked.
    """
    # Get the database session from request state
    # This will be set by a middleware or dependency
    db = getattr(request.state, "db", None)

    if db is None:
        # In development/testing, allow mock authentication
        settings = get_settings()
        if settings.is_development:
            return AuthenticatedUser(
                user_id="dev-user",
                api_key_id="dev-key",
                organization_id="dev-org",
                rate_limit=1000,
                permissions=["*"],
            )
        raise AuthenticationError(message="Database connection not available")

    # Import here to avoid circular imports
    from src.db.repositories.api_key import APIKeyRepository

    repo = APIKeyRepository(db)
    settings = get_settings()
    manager = APIKeyManager(settings)

    # Hash the API key for lookup
    key_hash = manager.hash_api_key(api_key)

    # Find the API key in database
    api_key_record = await repo.get_by_hash(key_hash)

    if api_key_record is None:
        raise InvalidAPIKeyError()

    if api_key_record.is_revoked:
        raise InvalidAPIKeyError(details={"reason": "API key has been revoked"})

    if api_key_record.expires_at and api_key_record.expires_at < datetime.now(
        timezone.utc
    ):
        raise InvalidAPIKeyError(details={"reason": "API key has expired"})

    # Update last used timestamp (fire and forget)
    await repo.update_last_used(api_key_record.id)

    return AuthenticatedUser(
        user_id=api_key_record.user_id,
        api_key_id=str(api_key_record.id),
        organization_id=api_key_record.organization_id,
        rate_limit=api_key_record.rate_limit or 60,
        permissions=api_key_record.permissions or [],
    )


# Type alias for dependency injection
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

"""
Storage backend factory.

Creates the appropriate storage backend based on configuration.
"""

from src.core.config import Settings, get_settings
from src.services.storage.base import StorageBackend
from src.services.storage.local import LocalStorageBackend
from src.services.storage.s3 import S3StorageBackend

# Singleton instance
_storage_backend: StorageBackend | None = None


def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """
    Get the configured storage backend.

    Factory function that creates the appropriate storage backend
    based on application settings. Uses singleton pattern for caching.

    Args:
        settings: Application settings. Uses default if None.

    Returns:
        Configured StorageBackend instance.

    Raises:
        ValueError: If storage backend type is invalid or misconfigured.
    """
    global _storage_backend

    if _storage_backend is not None:
        return _storage_backend

    if settings is None:
        settings = get_settings()

    if settings.storage_backend == "local":
        _storage_backend = LocalStorageBackend(
            base_path=settings.local_storage_path,
        )

    elif settings.storage_backend == "s3":
        if not settings.s3_access_key or not settings.s3_secret_key:
            raise ValueError(
                "S3 storage requires S3_ACCESS_KEY and S3_SECRET_KEY to be set"
            )

        _storage_backend = S3StorageBackend(
            bucket_name=settings.s3_bucket_name,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
        )

    else:
        raise ValueError(f"Unknown storage backend: {settings.storage_backend}")

    return _storage_backend


def reset_storage_backend() -> None:
    """Reset the storage backend singleton (for testing)."""
    global _storage_backend
    _storage_backend = None


def create_storage_backend(
    backend_type: str,
    **kwargs: object,
) -> StorageBackend:
    """
    Create a storage backend with custom configuration.

    This function allows creating storage backends with custom settings,
    useful for testing or multi-tenant scenarios.

    Args:
        backend_type: Type of backend ("local" or "s3").
        **kwargs: Backend-specific configuration.

    Returns:
        Configured StorageBackend instance.
    """
    if backend_type == "local":
        base_path = kwargs.get("base_path", "/tmp/lexia-storage")
        return LocalStorageBackend(base_path=str(base_path))

    elif backend_type == "s3":
        return S3StorageBackend(
            bucket_name=str(kwargs.get("bucket_name", "")),
            access_key=str(kwargs.get("access_key", "")),
            secret_key=str(kwargs.get("secret_key", "")),
            region=str(kwargs.get("region", "us-east-1")),
            endpoint_url=kwargs.get("endpoint_url"),  # type: ignore
        )

    else:
        raise ValueError(f"Unknown storage backend: {backend_type}")

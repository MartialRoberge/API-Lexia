"""Storage service abstraction for local filesystem and S3."""

from src.services.storage.base import StorageBackend, StorageFile
from src.services.storage.factory import get_storage_backend

__all__ = ["StorageBackend", "StorageFile", "get_storage_backend"]

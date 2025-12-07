"""
Abstract base class for storage backends.

Provides a consistent interface for both local filesystem and S3 storage.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, BinaryIO


@dataclass
class StorageFile:
    """Metadata about a stored file."""

    key: str  # Unique identifier/path
    size: int  # Size in bytes
    content_type: str  # MIME type
    created_at: datetime
    modified_at: datetime
    etag: str | None = None  # ETag for caching
    metadata: dict[str, str] | None = None  # Custom metadata

    @property
    def filename(self) -> str:
        """Get the filename from the key."""
        return Path(self.key).name

    @property
    def extension(self) -> str:
        """Get the file extension."""
        return Path(self.key).suffix.lower()


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StorageFile:
        """
        Upload a file to storage.

        Args:
            key: Unique identifier for the file.
            data: File content as bytes or file-like object.
            content_type: MIME type of the file.
            metadata: Optional custom metadata.

        Returns:
            StorageFile with upload details.

        Raises:
            StorageError: If upload fails.
        """
        ...

    @abstractmethod
    async def upload_from_path(
        self,
        key: str,
        file_path: Path | str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StorageFile:
        """
        Upload a file from local path to storage.

        Args:
            key: Unique identifier for the file.
            file_path: Local path to the file.
            content_type: MIME type (auto-detected if None).
            metadata: Optional custom metadata.

        Returns:
            StorageFile with upload details.
        """
        ...

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """
        Download a file from storage.

        Args:
            key: Unique identifier of the file.

        Returns:
            File content as bytes.

        Raises:
            FileNotFoundError: If file doesn't exist.
            StorageError: If download fails.
        """
        ...

    @abstractmethod
    async def download_to_path(self, key: str, file_path: Path | str) -> Path:
        """
        Download a file to a local path.

        Args:
            key: Unique identifier of the file.
            file_path: Local path to save the file.

        Returns:
            Path to the downloaded file.
        """
        ...

    @abstractmethod
    async def stream(self, key: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """
        Stream a file from storage in chunks.

        Args:
            key: Unique identifier of the file.
            chunk_size: Size of each chunk in bytes.

        Yields:
            Chunks of file content.
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a file from storage.

        Args:
            key: Unique identifier of the file.

        Returns:
            True if file was deleted, False if it didn't exist.
        """
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            key: Unique identifier of the file.

        Returns:
            True if file exists.
        """
        ...

    @abstractmethod
    async def get_info(self, key: str) -> StorageFile | None:
        """
        Get file metadata without downloading content.

        Args:
            key: Unique identifier of the file.

        Returns:
            StorageFile with metadata, or None if not found.
        """
        ...

    @abstractmethod
    async def list_files(
        self,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> list[StorageFile]:
        """
        List files in storage with optional prefix filter.

        Args:
            prefix: Filter files by key prefix.
            max_keys: Maximum number of files to return.

        Returns:
            List of StorageFile objects.
        """
        ...

    @abstractmethod
    async def get_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> str:
        """
        Generate a presigned URL for direct access.

        Args:
            key: Unique identifier of the file.
            expires_in: URL expiration time in seconds.
            for_upload: If True, generate upload URL.

        Returns:
            Presigned URL string.
        """
        ...

    @abstractmethod
    async def copy(self, source_key: str, dest_key: str) -> StorageFile:
        """
        Copy a file within storage.

        Args:
            source_key: Source file key.
            dest_key: Destination file key.

        Returns:
            StorageFile for the copied file.
        """
        ...

    @abstractmethod
    async def move(self, source_key: str, dest_key: str) -> StorageFile:
        """
        Move a file within storage.

        Args:
            source_key: Source file key.
            dest_key: Destination file key.

        Returns:
            StorageFile for the moved file.
        """
        ...

    def generate_key(
        self,
        filename: str,
        prefix: str = "",
        include_timestamp: bool = True,
    ) -> str:
        """
        Generate a unique storage key for a file.

        Args:
            filename: Original filename.
            prefix: Optional prefix/folder.
            include_timestamp: Include timestamp in key.

        Returns:
            Generated unique key.
        """
        import uuid
        from datetime import datetime

        # Sanitize filename
        safe_filename = Path(filename).name
        extension = Path(safe_filename).suffix

        # Generate unique ID
        unique_id = uuid.uuid4().hex[:12]

        if include_timestamp:
            timestamp = datetime.utcnow().strftime("%Y/%m/%d")
            if prefix:
                return f"{prefix}/{timestamp}/{unique_id}{extension}"
            return f"{timestamp}/{unique_id}{extension}"
        else:
            if prefix:
                return f"{prefix}/{unique_id}{extension}"
            return f"{unique_id}{extension}"

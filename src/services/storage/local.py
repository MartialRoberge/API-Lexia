"""
Local filesystem storage backend.

Implements StorageBackend for local file system storage.
Used for development and small-scale deployments.
"""

import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, BinaryIO

import aiofiles
import aiofiles.os

from src.core.exceptions import FileNotFoundError as StorageFileNotFoundError
from src.core.exceptions import StorageError
from src.services.storage.base import StorageBackend, StorageFile


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage implementation."""

    def __init__(self, base_path: str | Path) -> None:
        """
        Initialize local storage backend.

        Args:
            base_path: Root directory for file storage.
        """
        self.base_path = Path(base_path).resolve()
        # Ensure base path exists
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, key: str) -> Path:
        """Get full filesystem path for a key."""
        # Prevent directory traversal attacks
        clean_key = key.lstrip("/").lstrip("\\")
        full_path = (self.base_path / clean_key).resolve()

        if not str(full_path).startswith(str(self.base_path)):
            raise StorageError(
                message="Invalid file key",
                details={"key": key, "reason": "Path traversal detected"},
            )

        return full_path

    def _get_content_type(self, path: Path) -> str:
        """Guess content type from file extension."""
        content_type, _ = mimetypes.guess_type(str(path))
        return content_type or "application/octet-stream"

    def _create_storage_file(self, path: Path, key: str) -> StorageFile:
        """Create StorageFile from filesystem path."""
        stat = path.stat()
        return StorageFile(
            key=key,
            size=stat.st_size,
            content_type=self._get_content_type(path),
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            etag=f"{stat.st_mtime}-{stat.st_size}",
        )

    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StorageFile:
        """Upload file to local storage."""
        full_path = self._get_full_path(key)

        try:
            # Create parent directories
            await aiofiles.os.makedirs(full_path.parent, exist_ok=True)

            # Write file
            if isinstance(data, bytes):
                async with aiofiles.open(full_path, "wb") as f:
                    await f.write(data)
            else:
                # Handle file-like object
                async with aiofiles.open(full_path, "wb") as f:
                    while chunk := data.read(8192):
                        await f.write(chunk)

            return self._create_storage_file(full_path, key)

        except OSError as e:
            raise StorageError(
                message=f"Failed to upload file: {e}",
                details={"key": key},
            ) from e

    async def upload_from_path(
        self,
        key: str,
        file_path: Path | str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StorageFile:
        """Upload file from local path."""
        source_path = Path(file_path)
        if not source_path.exists():
            raise StorageFileNotFoundError(
                message=f"Source file not found: {file_path}"
            )

        full_path = self._get_full_path(key)

        try:
            # Create parent directories
            await aiofiles.os.makedirs(full_path.parent, exist_ok=True)

            # Copy file
            loop = __import__("asyncio").get_event_loop()
            await loop.run_in_executor(
                None, shutil.copy2, str(source_path), str(full_path)
            )

            return self._create_storage_file(full_path, key)

        except OSError as e:
            raise StorageError(
                message=f"Failed to upload file: {e}",
                details={"key": key, "source": str(file_path)},
            ) from e

    async def download(self, key: str) -> bytes:
        """Download file from local storage."""
        full_path = self._get_full_path(key)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                message=f"File not found: {key}",
                details={"key": key},
            )

        try:
            async with aiofiles.open(full_path, "rb") as f:
                return await f.read()
        except OSError as e:
            raise StorageError(
                message=f"Failed to download file: {e}",
                details={"key": key},
            ) from e

    async def download_to_path(self, key: str, file_path: Path | str) -> Path:
        """Download file to local path."""
        full_path = self._get_full_path(key)
        dest_path = Path(file_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                message=f"File not found: {key}",
                details={"key": key},
            )

        try:
            # Create parent directories
            await aiofiles.os.makedirs(dest_path.parent, exist_ok=True)

            # Copy file
            loop = __import__("asyncio").get_event_loop()
            await loop.run_in_executor(
                None, shutil.copy2, str(full_path), str(dest_path)
            )

            return dest_path

        except OSError as e:
            raise StorageError(
                message=f"Failed to download file: {e}",
                details={"key": key, "destination": str(file_path)},
            ) from e

    async def stream(self, key: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """Stream file content in chunks."""
        full_path = self._get_full_path(key)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                message=f"File not found: {key}",
                details={"key": key},
            )

        try:
            async with aiofiles.open(full_path, "rb") as f:
                while chunk := await f.read(chunk_size):
                    yield chunk
        except OSError as e:
            raise StorageError(
                message=f"Failed to stream file: {e}",
                details={"key": key},
            ) from e

    async def delete(self, key: str) -> bool:
        """Delete file from local storage."""
        full_path = self._get_full_path(key)

        if not full_path.exists():
            return False

        try:
            await aiofiles.os.remove(full_path)

            # Clean up empty parent directories
            parent = full_path.parent
            while parent != self.base_path:
                try:
                    if not any(parent.iterdir()):
                        await aiofiles.os.rmdir(parent)
                        parent = parent.parent
                    else:
                        break
                except OSError:
                    break

            return True

        except OSError as e:
            raise StorageError(
                message=f"Failed to delete file: {e}",
                details={"key": key},
            ) from e

    async def exists(self, key: str) -> bool:
        """Check if file exists."""
        full_path = self._get_full_path(key)
        return full_path.exists() and full_path.is_file()

    async def get_info(self, key: str) -> StorageFile | None:
        """Get file metadata."""
        full_path = self._get_full_path(key)

        if not full_path.exists() or not full_path.is_file():
            return None

        return self._create_storage_file(full_path, key)

    async def list_files(
        self,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> list[StorageFile]:
        """List files with optional prefix filter."""
        if prefix:
            search_path = self._get_full_path(prefix)
        else:
            search_path = self.base_path

        if not search_path.exists():
            return []

        files: list[StorageFile] = []
        count = 0

        for path in search_path.rglob("*"):
            if path.is_file() and count < max_keys:
                # Convert to relative key
                key = str(path.relative_to(self.base_path))
                files.append(self._create_storage_file(path, key))
                count += 1

        return files

    async def get_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> str:
        """
        Generate a file URL.

        Note: Local storage doesn't support true presigned URLs.
        Returns a file:// URL for local access.
        """
        full_path = self._get_full_path(key)
        return f"file://{full_path}"

    async def copy(self, source_key: str, dest_key: str) -> StorageFile:
        """Copy file within storage."""
        source_path = self._get_full_path(source_key)
        dest_path = self._get_full_path(dest_key)

        if not source_path.exists():
            raise StorageFileNotFoundError(
                message=f"Source file not found: {source_key}",
                details={"key": source_key},
            )

        try:
            # Create parent directories
            await aiofiles.os.makedirs(dest_path.parent, exist_ok=True)

            # Copy file
            loop = __import__("asyncio").get_event_loop()
            await loop.run_in_executor(
                None, shutil.copy2, str(source_path), str(dest_path)
            )

            return self._create_storage_file(dest_path, dest_key)

        except OSError as e:
            raise StorageError(
                message=f"Failed to copy file: {e}",
                details={"source": source_key, "destination": dest_key},
            ) from e

    async def move(self, source_key: str, dest_key: str) -> StorageFile:
        """Move file within storage."""
        # Copy then delete
        result = await self.copy(source_key, dest_key)
        await self.delete(source_key)
        return result

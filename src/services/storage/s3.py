"""
S3/MinIO storage backend.

Implements StorageBackend for Amazon S3 and S3-compatible services (MinIO, etc.).
"""

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, BinaryIO

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from src.core.exceptions import FileNotFoundError as StorageFileNotFoundError
from src.core.exceptions import StorageError
from src.services.storage.base import StorageBackend, StorageFile


class S3StorageBackend(StorageBackend):
    """S3/MinIO storage implementation."""

    def __init__(
        self,
        bucket_name: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
    ) -> None:
        """
        Initialize S3 storage backend.

        Args:
            bucket_name: S3 bucket name.
            access_key: AWS access key ID.
            secret_key: AWS secret access key.
            region: AWS region.
            endpoint_url: Custom endpoint URL (for MinIO/self-hosted).
        """
        self.bucket_name = bucket_name
        self.region = region
        self.endpoint_url = endpoint_url

        # Create session
        self.session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

        # Configure client
        self.client_config = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path" if endpoint_url else "auto"},
        )

    def _get_content_type(self, key: str) -> str:
        """Guess content type from file extension."""
        content_type, _ = mimetypes.guess_type(key)
        return content_type or "application/octet-stream"

    def _parse_s3_response(self, key: str, response: dict) -> StorageFile:
        """Parse S3 response to StorageFile."""
        return StorageFile(
            key=key,
            size=response.get("ContentLength", 0),
            content_type=response.get("ContentType", "application/octet-stream"),
            created_at=response.get("LastModified", datetime.now(timezone.utc)),
            modified_at=response.get("LastModified", datetime.now(timezone.utc)),
            etag=response.get("ETag", "").strip('"'),
            metadata=response.get("Metadata"),
        )

    async def _get_client(self) -> object:
        """Get S3 client context manager."""
        return self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=self.client_config,
        )

    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StorageFile:
        """Upload file to S3."""
        try:
            async with await self._get_client() as client:
                extra_args: dict = {"ContentType": content_type}
                if metadata:
                    extra_args["Metadata"] = metadata

                if isinstance(data, bytes):
                    await client.put_object(
                        Bucket=self.bucket_name,
                        Key=key,
                        Body=data,
                        **extra_args,
                    )
                else:
                    await client.upload_fileobj(
                        data,
                        self.bucket_name,
                        key,
                        ExtraArgs=extra_args,
                    )

                # Get object info
                response = await client.head_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )
                return self._parse_s3_response(key, response)

        except ClientError as e:
            raise StorageError(
                message=f"Failed to upload to S3: {e}",
                details={"key": key, "bucket": self.bucket_name},
            ) from e

    async def upload_from_path(
        self,
        key: str,
        file_path: Path | str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StorageFile:
        """Upload file from local path to S3."""
        path = Path(file_path)
        if not path.exists():
            raise StorageFileNotFoundError(
                message=f"Source file not found: {file_path}"
            )

        if content_type is None:
            content_type = self._get_content_type(key)

        try:
            async with await self._get_client() as client:
                extra_args: dict = {"ContentType": content_type}
                if metadata:
                    extra_args["Metadata"] = metadata

                await client.upload_file(
                    str(path),
                    self.bucket_name,
                    key,
                    ExtraArgs=extra_args,
                )

                response = await client.head_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )
                return self._parse_s3_response(key, response)

        except ClientError as e:
            raise StorageError(
                message=f"Failed to upload to S3: {e}",
                details={"key": key, "source": str(file_path)},
            ) from e

    async def download(self, key: str) -> bytes:
        """Download file from S3."""
        try:
            async with await self._get_client() as client:
                response = await client.get_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )
                async with response["Body"] as stream:
                    return await stream.read()

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise StorageFileNotFoundError(
                    message=f"File not found: {key}",
                    details={"key": key},
                ) from e
            raise StorageError(
                message=f"Failed to download from S3: {e}",
                details={"key": key},
            ) from e

    async def download_to_path(self, key: str, file_path: Path | str) -> Path:
        """Download file to local path."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with await self._get_client() as client:
                await client.download_file(
                    self.bucket_name,
                    key,
                    str(path),
                )
                return path

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise StorageFileNotFoundError(
                    message=f"File not found: {key}",
                    details={"key": key},
                ) from e
            raise StorageError(
                message=f"Failed to download from S3: {e}",
                details={"key": key},
            ) from e

    async def stream(self, key: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """Stream file content in chunks."""
        try:
            async with await self._get_client() as client:
                response = await client.get_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )
                async with response["Body"] as stream:
                    while chunk := await stream.read(chunk_size):
                        yield chunk

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise StorageFileNotFoundError(
                    message=f"File not found: {key}",
                    details={"key": key},
                ) from e
            raise StorageError(
                message=f"Failed to stream from S3: {e}",
                details={"key": key},
            ) from e

    async def delete(self, key: str) -> bool:
        """Delete file from S3."""
        try:
            async with await self._get_client() as client:
                # Check if exists first
                try:
                    await client.head_object(Bucket=self.bucket_name, Key=key)
                except ClientError as e:
                    if e.response["Error"]["Code"] == "404":
                        return False
                    raise

                await client.delete_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )
                return True

        except ClientError as e:
            raise StorageError(
                message=f"Failed to delete from S3: {e}",
                details={"key": key},
            ) from e

    async def exists(self, key: str) -> bool:
        """Check if file exists in S3."""
        try:
            async with await self._get_client() as client:
                await client.head_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise StorageError(
                message=f"Failed to check file existence: {e}",
                details={"key": key},
            ) from e

    async def get_info(self, key: str) -> StorageFile | None:
        """Get file metadata from S3."""
        try:
            async with await self._get_client() as client:
                response = await client.head_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )
                return self._parse_s3_response(key, response)

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            raise StorageError(
                message=f"Failed to get file info: {e}",
                details={"key": key},
            ) from e

    async def list_files(
        self,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> list[StorageFile]:
        """List files in S3 bucket."""
        files: list[StorageFile] = []

        try:
            async with await self._get_client() as client:
                paginator = client.get_paginator("list_objects_v2")
                async for page in paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=prefix,
                    PaginationConfig={"MaxItems": max_keys},
                ):
                    for obj in page.get("Contents", []):
                        files.append(
                            StorageFile(
                                key=obj["Key"],
                                size=obj["Size"],
                                content_type=self._get_content_type(obj["Key"]),
                                created_at=obj["LastModified"],
                                modified_at=obj["LastModified"],
                                etag=obj.get("ETag", "").strip('"'),
                            )
                        )

            return files

        except ClientError as e:
            raise StorageError(
                message=f"Failed to list files: {e}",
                details={"prefix": prefix},
            ) from e

    async def get_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> str:
        """Generate presigned URL for direct access."""
        try:
            async with await self._get_client() as client:
                if for_upload:
                    url = await client.generate_presigned_url(
                        "put_object",
                        Params={"Bucket": self.bucket_name, "Key": key},
                        ExpiresIn=expires_in,
                    )
                else:
                    url = await client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": self.bucket_name, "Key": key},
                        ExpiresIn=expires_in,
                    )
                return url

        except ClientError as e:
            raise StorageError(
                message=f"Failed to generate presigned URL: {e}",
                details={"key": key},
            ) from e

    async def copy(self, source_key: str, dest_key: str) -> StorageFile:
        """Copy file within S3."""
        try:
            async with await self._get_client() as client:
                await client.copy_object(
                    Bucket=self.bucket_name,
                    CopySource={"Bucket": self.bucket_name, "Key": source_key},
                    Key=dest_key,
                )

                response = await client.head_object(
                    Bucket=self.bucket_name,
                    Key=dest_key,
                )
                return self._parse_s3_response(dest_key, response)

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise StorageFileNotFoundError(
                    message=f"Source file not found: {source_key}",
                    details={"key": source_key},
                ) from e
            raise StorageError(
                message=f"Failed to copy file: {e}",
                details={"source": source_key, "destination": dest_key},
            ) from e

    async def move(self, source_key: str, dest_key: str) -> StorageFile:
        """Move file within S3."""
        result = await self.copy(source_key, dest_key)
        await self.delete(source_key)
        return result

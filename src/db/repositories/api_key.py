"""
Repository for API Key operations.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import APIKey


class APIKeyRepository:
    """Repository for API key CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        key_hash: str,
        name: str,
        user_id: str,
        organization_id: str | None = None,
        permissions: list[str] | None = None,
        rate_limit: int = 60,
        expires_at: datetime | None = None,
    ) -> APIKey:
        """Create a new API key."""
        api_key = APIKey(
            key_hash=key_hash,
            name=name,
            user_id=user_id,
            organization_id=organization_id,
            permissions=permissions or ["*"],
            rate_limit=rate_limit,
            expires_at=expires_at,
        )
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def get_by_id(self, key_id: uuid.UUID) -> APIKey | None:
        """Get API key by ID."""
        result = await self.session.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> APIKey | None:
        """Get API key by hash."""
        result = await self.session.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: str,
        include_revoked: bool = False,
    ) -> list[APIKey]:
        """Get all API keys for a user."""
        query = select(APIKey).where(APIKey.user_id == user_id)
        if not include_revoked:
            query = query.where(APIKey.is_revoked == False)  # noqa: E712
        result = await self.session.execute(query.order_by(APIKey.created_at.desc()))
        return list(result.scalars().all())

    async def update_last_used(self, key_id: uuid.UUID) -> None:
        """Update last used timestamp."""
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(last_used_at=datetime.now(timezone.utc))
        )

    async def revoke(self, key_id: uuid.UUID) -> bool:
        """Revoke an API key."""
        result = await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(is_revoked=True)
        )
        return result.rowcount > 0

    async def delete(self, key_id: uuid.UUID) -> bool:
        """Delete an API key."""
        api_key = await self.get_by_id(key_id)
        if api_key:
            await self.session.delete(api_key)
            return True
        return False

"""
Repository for Job operations.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Job


class JobRepository:
    """Repository for job CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        job_type: str,
        params: dict[str, Any] | None = None,
        priority: str = "normal",
        user_id: str | None = None,
        api_key_id: uuid.UUID | None = None,
        webhook_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Job:
        """Create a new job."""
        job = Job(
            type=job_type,
            status="pending",
            priority=priority,
            params=params,
            user_id=user_id,
            api_key_id=api_key_id,
            webhook_url=webhook_url,
            metadata=metadata,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        """Get job by ID."""
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_by_celery_task_id(self, task_id: str) -> Job | None:
        """Get job by Celery task ID."""
        result = await self.session.execute(
            select(Job).where(Job.celery_task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: str,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """Get jobs for a user."""
        query = select(Job).where(Job.user_id == user_id)

        if status:
            query = query.where(Job.status == status)
        if job_type:
            query = query.where(Job.type == job_type)

        query = query.order_by(Job.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        job_id: uuid.UUID,
        status: str,
        error_message: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Update job status."""
        values: dict[str, Any] = {"status": status}

        if status == "processing":
            values["started_at"] = datetime.now(timezone.utc)
        elif status in ("completed", "failed"):
            values["completed_at"] = datetime.now(timezone.utc)

        if error_message:
            values["error_message"] = error_message
        if error_code:
            values["error_code"] = error_code

        await self.session.execute(
            update(Job).where(Job.id == job_id).values(**values)
        )

    async def update_progress(
        self,
        job_id: uuid.UUID,
        percent: int,
        message: str | None = None,
    ) -> None:
        """Update job progress."""
        values: dict[str, Any] = {"progress_percent": percent}
        if message:
            values["progress_message"] = message

        await self.session.execute(
            update(Job).where(Job.id == job_id).values(**values)
        )

    async def set_result(
        self,
        job_id: uuid.UUID,
        result: dict[str, Any] | None = None,
        result_url: str | None = None,
    ) -> None:
        """Set job result."""
        values: dict[str, Any] = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "progress_percent": 100,
        }
        if result:
            values["result"] = result
        if result_url:
            values["result_url"] = result_url

        await self.session.execute(
            update(Job).where(Job.id == job_id).values(**values)
        )

    async def set_celery_task_id(
        self,
        job_id: uuid.UUID,
        celery_task_id: str,
    ) -> None:
        """Set Celery task ID."""
        await self.session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(celery_task_id=celery_task_id, status="queued")
        )

    async def mark_webhook_sent(self, job_id: uuid.UUID) -> None:
        """Mark webhook as sent."""
        await self.session.execute(
            update(Job).where(Job.id == job_id).values(webhook_sent=True)
        )

    async def get_pending_webhooks(self, limit: int = 100) -> list[Job]:
        """Get completed jobs with unsent webhooks."""
        result = await self.session.execute(
            select(Job)
            .where(Job.status.in_(["completed", "failed"]))
            .where(Job.webhook_url.isnot(None))
            .where(Job.webhook_sent == False)  # noqa: E712
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: str,
        status: str | None = None,
    ) -> int:
        """Count jobs for a user."""
        from sqlalchemy import func

        query = select(func.count(Job.id)).where(Job.user_id == user_id)
        if status:
            query = query.where(Job.status == status)

        result = await self.session.execute(query)
        return result.scalar_one()

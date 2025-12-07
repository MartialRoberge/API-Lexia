"""
Webhook tasks for Celery.
"""

import asyncio

import httpx

from src.workers.celery_app import app


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(
    name="src.workers.tasks.webhooks.send_webhook",
    max_retries=5,
    default_retry_delay=30,
)
def send_webhook(
    job_id: str,
    webhook_url: str,
    payload: dict,
    auth_header: str | None = None,
):
    """
    Send webhook notification.

    Args:
        job_id: Job ID for logging.
        webhook_url: URL to send webhook to.
        payload: JSON payload to send.
        auth_header: Optional authorization header.
    """
    return run_async(
        _send_webhook_async(job_id, webhook_url, payload, auth_header)
    )


async def _send_webhook_async(
    job_id: str,
    webhook_url: str,
    payload: dict,
    auth_header: str | None,
):
    """Async webhook sender."""
    from src.core.logging import get_logger

    logger = get_logger(__name__)

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()

        logger.info(
            "webhook_sent",
            job_id=job_id,
            url=webhook_url,
            status=response.status_code,
        )

        return {"status": "success", "status_code": response.status_code}

    except httpx.HTTPStatusError as e:
        logger.warning(
            "webhook_failed",
            job_id=job_id,
            url=webhook_url,
            status=e.response.status_code,
        )
        raise

    except httpx.RequestError as e:
        logger.warning(
            "webhook_error",
            job_id=job_id,
            url=webhook_url,
            error=str(e),
        )
        raise


@app.task(name="src.workers.tasks.webhooks.send_pending_webhooks")
def send_pending_webhooks():
    """Send all pending webhooks (scheduled task)."""
    return run_async(_send_pending_webhooks_async())


async def _send_pending_webhooks_async():
    """Process all pending webhooks."""
    import uuid

    from src.core.logging import get_logger
    from src.db.repositories.job import JobRepository
    from src.db.session import get_db_context

    logger = get_logger(__name__)

    async with get_db_context() as db:
        job_repo = JobRepository(db)
        pending_jobs = await job_repo.get_pending_webhooks(limit=50)

        sent_count = 0
        for job in pending_jobs:
            if not job.webhook_url:
                continue

            payload = {
                "event": f"job.{job.status}",
                "job_id": str(job.id),
                "job_type": job.type,
                "status": job.status,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "result_url": job.result_url,
            }

            if job.error_code:
                payload["error"] = {
                    "code": job.error_code,
                    "message": job.error_message,
                }

            try:
                # Queue the webhook
                send_webhook.delay(
                    str(job.id),
                    job.webhook_url,
                    payload,
                )
                await job_repo.mark_webhook_sent(job.id)
                sent_count += 1

            except Exception as e:
                logger.error(
                    "webhook_queue_error",
                    job_id=str(job.id),
                    error=str(e),
                )

    logger.info("pending_webhooks_processed", count=sent_count)
    return {"sent": sent_count}

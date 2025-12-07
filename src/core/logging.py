"""
Structured logging configuration using structlog.

Provides consistent JSON logging for production and pretty console output for development.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from src.core.config import Settings, get_settings


def configure_logging(settings: Settings | None = None) -> None:
    """
    Configure structured logging for the application.

    Args:
        settings: Application settings. If None, uses default settings.
    """
    if settings is None:
        settings = get_settings()

    # Set log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Common processors for both dev and prod
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.log_format == "json":
        # Production: JSON format
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Pretty console output
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Set levels for noisy libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name. If None, uses the caller's module name.

    Returns:
        A bound structlog logger.
    """
    return structlog.get_logger(name)


class RequestLogger:
    """Logger for HTTP request/response logging."""

    def __init__(self) -> None:
        self.logger = get_logger("http")

    def log_request(
        self,
        method: str,
        path: str,
        client_ip: str | None = None,
        user_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Log incoming HTTP request."""
        self.logger.info(
            "request_received",
            method=method,
            path=path,
            client_ip=client_ip,
            user_id=user_id,
        )

    def log_response(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: str | None = None,
    ) -> None:
        """Log HTTP response."""
        log_method = self.logger.info if status_code < 400 else self.logger.warning
        log_method(
            "request_completed",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            user_id=user_id,
        )


class JobLogger:
    """Logger for async job processing."""

    def __init__(self) -> None:
        self.logger = get_logger("jobs")

    def log_job_started(
        self,
        job_id: str,
        job_type: str,
        user_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Log job start."""
        self.logger.info(
            "job_started",
            job_id=job_id,
            job_type=job_type,
            user_id=user_id,
            params=params,
        )

    def log_job_completed(
        self,
        job_id: str,
        job_type: str,
        duration_seconds: float,
        result_size: int | None = None,
    ) -> None:
        """Log job completion."""
        self.logger.info(
            "job_completed",
            job_id=job_id,
            job_type=job_type,
            duration_seconds=round(duration_seconds, 2),
            result_size=result_size,
        )

    def log_job_failed(
        self,
        job_id: str,
        job_type: str,
        error: str,
        duration_seconds: float | None = None,
    ) -> None:
        """Log job failure."""
        self.logger.error(
            "job_failed",
            job_id=job_id,
            job_type=job_type,
            error=error,
            duration_seconds=round(duration_seconds, 2) if duration_seconds else None,
        )


class ModelLogger:
    """Logger for ML model inference."""

    def __init__(self) -> None:
        self.logger = get_logger("models")

    def log_inference_started(
        self,
        model_id: str,
        model_type: str,
        input_size: int | None = None,
    ) -> None:
        """Log inference start."""
        self.logger.debug(
            "inference_started",
            model_id=model_id,
            model_type=model_type,
            input_size=input_size,
        )

    def log_inference_completed(
        self,
        model_id: str,
        model_type: str,
        duration_ms: float,
        tokens_generated: int | None = None,
    ) -> None:
        """Log inference completion."""
        self.logger.info(
            "inference_completed",
            model_id=model_id,
            model_type=model_type,
            duration_ms=round(duration_ms, 2),
            tokens_generated=tokens_generated,
        )

    def log_inference_failed(
        self,
        model_id: str,
        model_type: str,
        error: str,
    ) -> None:
        """Log inference failure."""
        self.logger.error(
            "inference_failed",
            model_id=model_id,
            model_type=model_type,
            error=error,
        )

"""
Lexia API - Main FastAPI Application.

Production-ready API for LLM inference, Speech-to-Text, and Speaker Diarization.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import Settings, get_settings
from src.core.exceptions import LexiaAPIError
from src.core.logging import configure_logging, get_logger
from src.db.session import close_db, init_db, get_session_maker
from src.models.common import ErrorDetail, ErrorResponse, HealthResponse


class DatabaseMiddleware(BaseHTTPMiddleware):
    """Middleware to inject database session into request state."""

    async def dispatch(self, request: Request, call_next):
        """Inject database session into request.state.db."""
        session_maker = get_session_maker()
        async with session_maker() as session:
            request.state.db = session
            try:
                response = await call_next(request)
                await session.commit()
                return response
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

# Import routers
from src.api.routers import diarization, jobs, llm, stt


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    settings = get_settings()

    # Startup
    logger.info("starting_application", env=settings.app_env)
    configure_logging(settings)

    # Initialize database
    try:
        await init_db()
        logger.info("database_connected")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))

    yield

    # Shutdown
    logger.info("shutting_down_application")
    await close_db()


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        settings: Application settings. Uses default if None.

    Returns:
        Configured FastAPI application.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="Lexia API",
        description="""
# Lexia API

Production-ready API for AI-powered audio processing and language models.

## Features

### LLM (Large Language Model)
- Chat completion with streaming support
- Tool/function calling
- Multiple model support

### Speech-to-Text
- Async transcription with job polling
- Sync transcription for short files
- Word-level timestamps
- Multi-language support (French, English, etc.)

### Speaker Diarization
- Automatic speaker detection
- Configurable speaker count
- Overlap detection
- RTTM output format

## Authentication

All endpoints require API key authentication.

```
Authorization: Bearer lx_your_api_key
```

## Rate Limits

Rate limits are applied per API key. Check response headers:
- `X-RateLimit-Limit`: Requests allowed per minute
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Reset timestamp

---

**Version:** 1.0.0 | **Contact:** contact@lexia.fr
        """,
        version="1.0.0",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "LLM", "description": "Large Language Model endpoints"},
            {"name": "Speech-to-Text", "description": "Audio transcription endpoints"},
            {"name": "Diarization", "description": "Speaker diarization endpoints"},
            {"name": "Jobs", "description": "Async job management"},
            {"name": "Health", "description": "Health check endpoints"},
        ],
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Database middleware - injects db session into request.state.db
    app.add_middleware(DatabaseMiddleware)

    # Exception handlers
    @app.exception_handler(LexiaAPIError)
    async def lexia_error_handler(
        request: Request, exc: LexiaAPIError
    ) -> JSONResponse:
        """Handle Lexia API errors."""
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle validation errors."""
        errors = []
        for error in exc.errors():
            errors.append({
                "loc": error.get("loc", []),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            })

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Request validation failed",
                    details={"errors": errors},
                    path=str(request.url.path),
                )
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def general_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected errors."""
        logger.exception("unhandled_error", path=request.url.path)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="An unexpected error occurred",
                    path=str(request.url.path),
                )
            ).model_dump(mode="json"),
        )

    # Include routers
    app.include_router(llm.router)
    app.include_router(stt.router)
    app.include_router(diarization.router)
    app.include_router(jobs.router)

    # Health endpoints
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check",
        description="Check API health and dependent services status.",
    )
    async def health_check() -> HealthResponse:
        """Check API health."""
        services: dict[str, str] = {}

        # Check LLM service
        try:
            from src.services.llm.factory import get_llm_backend
            llm_backend = get_llm_backend(settings)
            if await llm_backend.health_check():
                services["llm"] = "healthy"
            else:
                services["llm"] = "unhealthy"
        except Exception:
            services["llm"] = "unavailable"

        # Check STT service
        try:
            from src.services.stt.factory import get_stt_backend
            stt_backend = get_stt_backend(settings)
            if await stt_backend.health_check():
                services["stt"] = "healthy"
            else:
                services["stt"] = "unhealthy"
        except Exception:
            services["stt"] = "unavailable"

        # Overall status
        all_healthy = all(s == "healthy" for s in services.values())

        return HealthResponse(
            status="healthy" if all_healthy else "degraded",
            version=settings.app_version,
            services=services,
        )

    @app.get(
        "/",
        include_in_schema=False,
    )
    async def root() -> dict[str, Any]:
        """Root endpoint."""
        return {
            "name": "Lexia API",
            "version": settings.app_version,
            "docs": "/redoc",
            "openapi": "/openapi.json",
        }

    return app


# Create default application instance
app = create_app()


def main() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        workers=settings.app_workers,
        reload=settings.is_development,
    )


if __name__ == "__main__":
    main()

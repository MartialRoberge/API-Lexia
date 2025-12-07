"""
Database session management.

Provides async database connection and session management.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings, get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Global engine and session maker
_engine = None
_async_session_maker = None


def get_engine(settings: Settings | None = None):
    """Get or create the async engine."""
    global _engine

    if _engine is None:
        if settings is None:
            settings = get_settings()

        _engine = create_async_engine(
            str(settings.database_url),
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,
            echo=settings.app_debug,
        )
        logger.info("database_engine_created")

    return _engine


def get_session_maker(settings: Settings | None = None) -> async_sessionmaker:
    """Get or create the session maker."""
    global _async_session_maker

    if _async_session_maker is None:
        engine = get_engine(settings)
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return _async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session as async generator.

    Usage as FastAPI dependency:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session as async context manager.

    Usage:
        async with get_db_context() as db:
            await db.execute(...)
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    from src.db.models import Base

    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_initialized")


async def close_db() -> None:
    """Close database connections."""
    global _engine, _async_session_maker

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None
        logger.info("database_connections_closed")

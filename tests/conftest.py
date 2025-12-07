"""
Pytest configuration and fixtures.
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import create_app
from src.core.config import Settings
from src.db.models import Base


# Test settings
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        app_env="development",
        app_debug=True,
        api_secret_key="test-secret-key-for-testing-only",
        api_key_salt="test-salt",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        use_mock_llm=True,
        use_mock_stt=True,
        use_mock_diarization=True,
        storage_backend="local",
        local_storage_path="/tmp/lexia-test",
    )


# Event loop for async tests
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# In-memory database for tests
@pytest_asyncio.fixture
async def db_engine():
    """Create in-memory SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for testing."""
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session


# Test client
@pytest_asyncio.fixture
async def client(test_settings: Settings) -> AsyncGenerator[AsyncClient, None]:
    """Create test client."""
    app = create_app(test_settings)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# Mock API key
@pytest.fixture
def api_key() -> str:
    """Return a mock API key for testing."""
    return "lx_test_api_key_for_unit_testing"


@pytest.fixture
def auth_headers(api_key: str) -> dict:
    """Return authorization headers."""
    return {"Authorization": f"Bearer {api_key}"}

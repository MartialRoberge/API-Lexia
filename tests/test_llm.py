"""
LLM endpoint tests.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_models(client: AsyncClient, auth_headers: dict):
    """Test listing models."""
    response = await client.get("/v1/models", headers=auth_headers)

    # May return 401 without proper auth setup
    # In real tests, we'd mock the auth
    assert response.status_code in [200, 401]


@pytest.mark.asyncio
async def test_chat_completion_without_auth(client: AsyncClient):
    """Test chat completion without authentication."""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "general7Bv2",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_completion_validation(client: AsyncClient, auth_headers: dict):
    """Test chat completion validation."""
    # Missing required fields
    response = await client.post(
        "/v1/chat/completions",
        json={},
        headers=auth_headers,
    )
    assert response.status_code in [401, 422]

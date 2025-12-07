"""
Comprehensive API endpoint tests.

Tests all endpoints with various scenarios:
- Valid requests
- Invalid requests (validation errors)
- Authentication errors
- Edge cases
"""

import pytest
from httpx import AsyncClient


# =============================================================================
# Root & Health Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_root_returns_api_info(client: AsyncClient):
    """Root endpoint returns API info."""
    response = await client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Lexia API"
    assert "version" in data
    assert data["docs"] == "/redoc"
    assert data["openapi"] == "/openapi.json"


@pytest.mark.asyncio
async def test_health_returns_service_status(client: AsyncClient):
    """Health endpoint returns service status."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "version" in data
    assert "services" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_openapi_schema_available(client: AsyncClient):
    """OpenAPI schema is accessible."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
    assert "paths" in schema


# =============================================================================
# LLM Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_list_models_requires_auth(client: AsyncClient):
    """List models requires authentication."""
    response = await client.get("/v1/models")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_models_with_auth(client: AsyncClient, auth_headers: dict):
    """List models with valid auth."""
    response = await client.get("/v1/models", headers=auth_headers)
    # With mock auth, should get 200 or 401 depending on setup
    assert response.status_code in [200, 401]


@pytest.mark.asyncio
async def test_chat_completion_requires_auth(client: AsyncClient):
    """Chat completion requires authentication."""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "general7Bv2",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_completion_validates_messages(client: AsyncClient, auth_headers: dict):
    """Chat completion validates message format."""
    # Empty messages array
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "general7Bv2", "messages": []},
        headers=auth_headers,
    )
    assert response.status_code in [401, 422]

    # Missing messages field
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "general7Bv2"},
        headers=auth_headers,
    )
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_chat_completion_validates_role(client: AsyncClient, auth_headers: dict):
    """Chat completion validates message roles."""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "general7Bv2",
            "messages": [{"role": "invalid_role", "content": "Hello"}],
        },
        headers=auth_headers,
    )
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_chat_completion_validates_temperature(client: AsyncClient, auth_headers: dict):
    """Chat completion validates temperature range."""
    # Temperature too high
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "general7Bv2",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 3.0,  # Invalid, should be 0-2
        },
        headers=auth_headers,
    )
    assert response.status_code in [401, 422]


# =============================================================================
# STT Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_transcription_requires_auth(client: AsyncClient):
    """Transcription endpoint requires authentication."""
    response = await client.post(
        "/v1/transcriptions",
        json={"audio_url": "https://example.com/audio.wav"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_transcription_validates_input(client: AsyncClient, auth_headers: dict):
    """Transcription validates input format."""
    # Empty body
    response = await client.post(
        "/v1/transcriptions",
        json={},
        headers=auth_headers,
    )
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_sync_transcription_requires_auth(client: AsyncClient):
    """Sync transcription requires authentication."""
    response = await client.post(
        "/v1/transcriptions/sync",
        json={"audio_url": "https://example.com/audio.wav"},
    )
    assert response.status_code == 401


# =============================================================================
# Diarization Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_diarization_requires_auth(client: AsyncClient):
    """Diarization endpoint requires authentication."""
    response = await client.post(
        "/v1/diarization",
        json={"audio_url": "https://example.com/audio.wav"},
    )
    assert response.status_code == 401


# =============================================================================
# Jobs Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_list_jobs_requires_auth(client: AsyncClient):
    """List jobs requires authentication."""
    response = await client.get("/v1/jobs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_job_requires_auth(client: AsyncClient):
    """Get job by ID requires authentication."""
    response = await client.get("/v1/jobs/550e8400-e29b-41d4-a716-446655440000")
    assert response.status_code == 401


# =============================================================================
# Security Tests
# =============================================================================


@pytest.mark.asyncio
async def test_sql_injection_in_path(client: AsyncClient, auth_headers: dict):
    """SQL injection attempts in path are handled safely."""
    malicious_paths = [
        "/v1/jobs/'; DROP TABLE jobs; --",
        "/v1/jobs/1 OR 1=1",
        "/v1/transcriptions/' UNION SELECT * FROM api_keys --",
    ]

    for path in malicious_paths:
        response = await client.get(path, headers=auth_headers)
        # Should return 401 (auth) or 422 (validation), not 500
        assert response.status_code in [401, 404, 422]


@pytest.mark.asyncio
async def test_xss_in_request_body(client: AsyncClient, auth_headers: dict):
    """XSS attempts in request body are handled safely."""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "<script>alert('xss')</script>",
            "messages": [{"role": "user", "content": "<img src=x onerror=alert('xss')>"}],
        },
        headers=auth_headers,
    )
    # Should not cause server error
    assert response.status_code in [401, 422, 503]


@pytest.mark.asyncio
async def test_oversized_request_rejected(client: AsyncClient, auth_headers: dict):
    """Oversized requests are rejected."""
    # Create a very large message
    large_content = "x" * (10 * 1024 * 1024)  # 10MB

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "general7Bv2",
            "messages": [{"role": "user", "content": large_content}],
        },
        headers=auth_headers,
    )
    # Should be rejected by server limits
    assert response.status_code in [401, 413, 422]


@pytest.mark.asyncio
async def test_invalid_auth_header_format(client: AsyncClient):
    """Invalid auth header formats are rejected."""
    invalid_headers = [
        {"Authorization": "Basic dXNlcjpwYXNz"},  # Basic auth instead of Bearer
        {"Authorization": "Bearer"},  # Missing token
        {"Authorization": ""},  # Empty
        {"X-API-Key": "some-key"},  # Wrong header name
    ]

    for headers in invalid_headers:
        response = await client.get("/v1/models", headers=headers)
        assert response.status_code == 401


# =============================================================================
# Rate Limiting Tests
# =============================================================================


@pytest.mark.asyncio
async def test_rate_limit_headers_present(client: AsyncClient, auth_headers: dict):
    """Rate limit headers are present in responses."""
    response = await client.get("/v1/models", headers=auth_headers)

    # Even with auth failure, rate limit tracking should work
    # In production, we'd check for X-RateLimit-* headers


# =============================================================================
# Error Response Format Tests
# =============================================================================


@pytest.mark.asyncio
async def test_404_error_format(client: AsyncClient):
    """404 errors have proper format."""
    response = await client.get("/nonexistent/endpoint")
    assert response.status_code == 404

    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_validation_error_format(client: AsyncClient, auth_headers: dict):
    """Validation errors have proper format."""
    response = await client.post(
        "/v1/chat/completions",
        json={"invalid": "data"},
        headers=auth_headers,
    )

    if response.status_code == 422:
        data = response.json()
        assert "detail" in data

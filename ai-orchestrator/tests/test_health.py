"""Tests for GET /health."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.main import app


async def _get_health() -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_health_ok(api_db):
    assert await _get_health() == {"status": "ok", "database": "healthy", "vector_store": "healthy"}


@pytest.mark.asyncio
async def test_health_reports_a_broken_vector_store(api_db, monkeypatch):
    monkeypatch.setattr(routes.vector_store, "health_check", lambda: False)
    body = await _get_health()
    assert body["vector_store"] == "unhealthy"

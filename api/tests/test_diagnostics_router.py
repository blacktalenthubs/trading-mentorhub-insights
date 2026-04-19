"""Tests for the diagnostics router — AI Updates report endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.diagnostics import AI_UPDATE_TYPES


def test_ai_update_types_covers_wait_and_resistance():
    assert "ai_scan_wait" in AI_UPDATE_TYPES
    assert "ai_resistance" in AI_UPDATE_TYPES


def test_ai_update_types_excludes_entries():
    assert "ai_day_long" not in AI_UPDATE_TYPES
    assert "ai_day_short" not in AI_UPDATE_TYPES
    assert "ai_swing_long" not in AI_UPDATE_TYPES
    assert "ai_swing_short" not in AI_UPDATE_TYPES
    assert "ai_exit_signal" not in AI_UPDATE_TYPES


@pytest.mark.asyncio
async def test_ai_updates_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/diagnostics/ai-updates?session_date=2026-04-18"
        )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_ai_updates_requires_session_date():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/diagnostics/ai-updates")
    assert resp.status_code == 422

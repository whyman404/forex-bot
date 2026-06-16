"""Test fixtures.

Atlas Goro — tests at this layer use ASGI in-process, not network.
Integration tests (marked) hit a real Postgres + Redis from docker-compose.test.yml.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# Ensure test env BEFORE any app import so Settings picks it up.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://forex:forex@localhost:5432/forex_bot_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes-long!!")
# 32-byte KEK base64 (all zeros — fine for tests, NEVER in prod)
os.environ.setdefault("ENCRYPTION_KEK_BASE64", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop so async fixtures can share state."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def app_instance():
    """Fresh FastAPI app per test (avoids leaked state)."""
    from app.main import create_app

    yield create_app()


@pytest_asyncio.fixture
async def client(app_instance) -> AsyncIterator:
    """Async HTTPX client bound to ASGI app — no real network."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

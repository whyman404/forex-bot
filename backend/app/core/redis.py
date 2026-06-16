"""Redis client factory — Railway + Upstash + self-hosted compatible.

Atlas Goro — fail-open philosophy. Redis powers rate limiting and the
email job queue; both are *eventually consistent* in our design. If
Redis is unreachable, we log loudly and let the app keep serving — a
brown-out is preferable to a hard down.

Supports:
- `redis://`   — plain TCP (Railway internal)
- `rediss://`  — TLS (Upstash, managed providers)

Connection options applied:
- `socket_timeout`     — caps a single op at 5 s
- `socket_connect_timeout` — caps initial handshake
- `retry_on_timeout`   — one retry for transient hiccups
- `health_check_interval` — 30 s ping while idle (kills dead conns early)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


def build_redis_client() -> "Redis | None":
    """Construct an async Redis client. Returns None if the redis package
    is missing or the URL is empty.

    Caller is responsible for `await client.ping()` to verify reachability;
    a returned object does NOT imply a working connection (lazy by default).
    """
    settings = get_settings()
    url = (settings.redis_url or "").strip()
    if not url:
        logger.warning("redis_url_empty_skipping")
        return None

    try:
        from redis.asyncio import Redis
    except ImportError as exc:
        logger.warning("redis_package_missing", err=str(exc))
        return None

    kwargs: dict = {
        "decode_responses": True,
        "socket_timeout": settings.redis_socket_timeout_seconds,
        "socket_connect_timeout": settings.redis_socket_timeout_seconds,
        "retry_on_timeout": True,
        "health_check_interval": 30,
    }
    # Note: `from_url` reads `rediss://` and enables TLS automatically; we don't
    # need to pass ssl=True. Upstash works out-of-the-box.
    return Redis.from_url(url, **kwargs)


async def ping_redis(client: "Redis | None", timeout_seconds: float = 2.0) -> bool:
    """Cheap liveness check for /readyz. Returns True iff PING succeeds in time."""
    if client is None:
        return False
    import asyncio as _asyncio

    try:
        return await _asyncio.wait_for(client.ping(), timeout=timeout_seconds)
    except Exception:  # noqa: BLE001
        return False


async def close_redis(client: "Redis | None") -> None:
    """Idempotent close — never raises."""
    if client is None:
        return
    try:
        # `aclose` is the new name in redis-py 5.x; fall back to `close` for older.
        if hasattr(client, "aclose"):
            await client.aclose()
        else:
            await client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_close_failed", err=str(exc))

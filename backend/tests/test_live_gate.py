"""Live-trading gate — all checks pass/fail in isolation.

Atlas Goro — unit tests for the gate logic using a fake AsyncSession-ish
shim so we don't need real DB. The gate is pure orchestration over query
results — easy to mock at the function level.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes-long!!")
os.environ.setdefault("ENCRYPTION_KEK_BASE64", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


pytestmark = pytest.mark.unit


def _user(*, verified: bool, totp: bool):
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        email="t@e",
        full_name="T",
        email_verified_at=datetime.now(UTC) if verified else None,
        totp_secret=b"x" if totp else None,
    )


@pytest.mark.asyncio
async def test_gate_fails_when_email_not_verified() -> None:
    from app.schemas.live import GateResult
    from app.services.live_gate_service import LiveGateService

    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value.scalar_one_or_none = MagicMock(
        return_value=SimpleNamespace(
            id="0", user_id="0", strategy_id="0", broker_account_id="0",
            status="paper", started_at=datetime.now(UTC) - timedelta(days=20),
            created_at=datetime.now(UTC) - timedelta(days=20),
            deleted_at=None,
        )
    )

    svc = LiveGateService(db)
    user = _user(verified=False, totp=True)
    # Patch sub-methods so the test only exercises email_verified branch
    svc._has_qualifying_backtest = AsyncMock(return_value=(True, None))  # type: ignore[assignment]
    svc._has_paper_track_record = AsyncMock(return_value=(True, None))  # type: ignore[assignment]
    svc._has_live_consent = AsyncMock(return_value=True)  # type: ignore[assignment]
    svc._check_broker_balance = MagicMock(return_value=(True, None))  # type: ignore[assignment]
    svc._global_kill_switch_clear = AsyncMock(return_value=(True, None))  # type: ignore[assignment]
    from app.services import subscription_guard

    subscription_guard.is_paid_user = AsyncMock(return_value=True)  # type: ignore[assignment]

    # Patch DB to return the same fake instance + strategy + broker.
    # We can't easily reach into _own_instance flow; instead patch can_go_live
    # at the boundary checks.
    from app.models.strategy import Strategy
    from app.models.broker_account import BrokerAccount

    strat = SimpleNamespace(
        id="s", code="london_breakout", asset_class="gold", risk_rating="medium"
    )
    broker = SimpleNamespace(balance_cached_cents=100_000)

    async def _exec(query):  # type: ignore[no-untyped-def]
        r = MagicMock()
        # Default — return None for unknown queries
        r.scalar_one_or_none = MagicMock(return_value=None)
        # crude type sniffing
        sql = str(query)
        if "FROM strategy_instances" in sql:
            r.scalar_one_or_none = MagicMock(
                return_value=SimpleNamespace(
                    id="i",
                    user_id=user.id,
                    strategy_id="s",
                    broker_account_id="b",
                    status="paper",
                    started_at=datetime.now(UTC) - timedelta(days=20),
                    created_at=datetime.now(UTC) - timedelta(days=20),
                    deleted_at=None,
                )
            )
        elif "FROM strategies" in sql:
            r.scalar_one_or_none = MagicMock(return_value=strat)
        elif "FROM broker_accounts" in sql:
            r.scalar_one_or_none = MagicMock(return_value=broker)
        return r

    db.execute = AsyncMock(side_effect=_exec)

    result = await svc.can_go_live("00000000-0000-0000-0000-000000000001", user)
    assert isinstance(result, GateResult)
    assert result.passed is False
    failed = {c.name for c in result.failed_checks}
    assert "email_verified" in failed


@pytest.mark.asyncio
async def test_gate_passes_when_all_clear() -> None:
    from app.services.live_gate_service import LiveGateService

    db = MagicMock()
    user = _user(verified=True, totp=True)

    async def _exec(query):  # type: ignore[no-untyped-def]
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=None)
        sql = str(query)
        if "FROM strategy_instances" in sql:
            r.scalar_one_or_none = MagicMock(
                return_value=SimpleNamespace(
                    id="i", user_id=user.id, strategy_id="s", broker_account_id="b",
                    status="paper",
                    started_at=datetime.now(UTC) - timedelta(days=30),
                    created_at=datetime.now(UTC) - timedelta(days=30),
                    deleted_at=None,
                )
            )
        elif "FROM strategies" in sql:
            r.scalar_one_or_none = MagicMock(
                return_value=SimpleNamespace(
                    id="s", code="london_breakout", asset_class="gold", risk_rating="medium"
                )
            )
        elif "FROM broker_accounts" in sql:
            r.scalar_one_or_none = MagicMock(
                return_value=SimpleNamespace(balance_cached_cents=100_000)
            )
        return r

    db.execute = AsyncMock(side_effect=_exec)
    svc = LiveGateService(db)
    svc._has_qualifying_backtest = AsyncMock(return_value=(True, None))  # type: ignore[assignment]
    svc._has_paper_track_record = AsyncMock(return_value=(True, None))  # type: ignore[assignment]
    svc._has_live_consent = AsyncMock(return_value=True)  # type: ignore[assignment]
    svc._check_broker_balance = MagicMock(return_value=(True, None))  # type: ignore[assignment]
    svc._global_kill_switch_clear = AsyncMock(return_value=(True, None))  # type: ignore[assignment]
    from app.services import subscription_guard

    subscription_guard.is_paid_user = AsyncMock(return_value=True)  # type: ignore[assignment]

    result = await svc.can_go_live("00000000-0000-0000-0000-000000000001", user)
    assert result.passed is True
    assert len(result.failed_checks) == 0

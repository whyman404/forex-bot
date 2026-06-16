"""Backtest use cases — enqueue + retrieve.

Enqueue strategy:
1. Persist `queued` row.
2. Push job to Redis list `backtest:queue` for trading-engine-worker (RQ-compatible).
3. Best-effort HTTP webhook to trading-engine (configurable). Both are optional.

Failure to enqueue is logged as a warning but does not roll back the DB row —
the worker may pick up the row by scanning `status='queued'` (catch-up sweep).
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import BacktestNotFoundError, StrategyNotFoundError
from app.core.logging import get_logger
from app.middleware.audit import record_audit
from app.models.backtest import Backtest
from app.models.strategy import Strategy
from app.schemas.backtest import (
    BacktestCreateRequest,
    BacktestPublic,
    EquityCurveResponse,
    EquityPoint,
)

logger = get_logger(__name__)


class BacktestService:
    def __init__(self, db: AsyncSession, *, redis=None) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.redis = redis

    async def enqueue(
        self, user_id: UUID, payload: BacktestCreateRequest
    ) -> BacktestPublic:
        # 1. Resolve strategy by code
        result = await self.db.execute(
            select(Strategy).where(Strategy.code == payload.strategy_code)
        )
        strategy = result.scalar_one_or_none()
        if strategy is None:
            raise StrategyNotFoundError()

        # 2. Persist queued row
        bt = Backtest(
            user_id=user_id,
            strategy_id=strategy.id,
            asset_symbol=payload.asset_symbol,
            timeframe=payload.timeframe,
            params=payload.params or {},
            start_date=payload.start_date,
            end_date=payload.end_date,
            status="queued",
        )
        self.db.add(bt)
        await self.db.flush()

        await record_audit(
            self.db,
            action="backtest.enqueued",
            actor_user_id=user_id,
            target_type="backtest",
            target_id=bt.id,
            payload={
                "strategy": payload.strategy_code,
                "symbol": payload.asset_symbol,
                "tf": payload.timeframe,
            },
        )
        await self.db.commit()
        await self.db.refresh(bt)

        # 3. Best-effort enqueue
        await self._publish_job(bt)

        return BacktestPublic.model_validate(bt)

    async def _publish_job(self, bt: Backtest) -> None:
        """Push to Redis queue. Tolerate Redis outage — the worker can sweep."""
        if self.redis is None:
            logger.info("backtest_enqueue_skipped_no_redis", backtest_id=str(bt.id))
            return
        try:
            await self.redis.lpush(
                "backtest:queue",
                json.dumps(
                    {
                        "backtest_id": str(bt.id),
                        "strategy_id": str(bt.strategy_id),
                        "asset": bt.asset_symbol,
                        "tf": bt.timeframe,
                        "start": bt.start_date.isoformat(),
                        "end": bt.end_date.isoformat(),
                        "params": bt.params,
                    }
                ),
            )
            logger.info("backtest_enqueued", backtest_id=str(bt.id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("backtest_enqueue_failed", err=str(exc))

    async def list_for_user(self, user_id: UUID) -> list[BacktestPublic]:
        result = await self.db.execute(
            select(Backtest)
            .where(Backtest.user_id == user_id)
            .order_by(Backtest.created_at.desc())
        )
        return [BacktestPublic.model_validate(b) for b in result.scalars().all()]

    async def get(self, user_id: UUID, backtest_id: UUID) -> BacktestPublic:
        result = await self.db.execute(
            select(Backtest).where(
                Backtest.id == backtest_id, Backtest.user_id == user_id
            )
        )
        b = result.scalar_one_or_none()
        if b is None:
            raise BacktestNotFoundError()
        return BacktestPublic.model_validate(b)

    async def equity_curve(self, user_id: UUID, backtest_id: UUID) -> EquityCurveResponse:
        """Return time-series. If `equity_curve_url` is set, signal client to fetch;
        otherwise (MVP) return an empty list — worker fills it once done.
        """
        result = await self.db.execute(
            select(Backtest).where(
                Backtest.id == backtest_id, Backtest.user_id == user_id
            )
        )
        b = result.scalar_one_or_none()
        if b is None:
            raise BacktestNotFoundError()

        # Phase 2: fetch from object storage if equity_curve_url is signed S3/MinIO.
        points: list[EquityPoint] = []
        return EquityCurveResponse(backtest_id=b.id, points=points)

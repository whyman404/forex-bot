"""Strategy + strategy instance use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    LiveGateFailedError,
    NotFoundError,
    StrategyInstanceConflictError,
    StrategyInstanceLockedError,
    StrategyNotFoundError,
    ValidationFailedError,
)
from app.core.logging import get_logger
from app.middleware.audit import record_audit
from app.models.broker_account import BrokerAccount
from app.models.strategy import Strategy
from app.models.strategy_instance import StrategyInstance
from app.models.user import User
from app.schemas.live import GateResult
from app.schemas.strategy import (
    StrategyInstanceCreateRequest,
    StrategyInstancePublic,
    StrategyInstanceUpdateRequest,
    StrategyPublic,
)
from app.schemas.tradingview import SUPPORTED_TV_INTERVALS

logger = get_logger(__name__)

# Params that cannot be edited while instance is live (require revert first).
HIGH_RISK_PARAM_KEYS: set[str] = {
    "risk_percent",
    "max_daily_loss_cents",
    "params",
}

# Strategies that need extra validation at create-time (Round 5).
TV_STRATEGY_CODES: set[str] = {"tv_signal"}


class StrategyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---- Catalog ---------------------------------------------------------

    async def list_catalog(self) -> list[StrategyPublic]:
        result = await self.db.execute(
            select(Strategy).where(Strategy.is_enabled.is_(True)).order_by(Strategy.code)
        )
        return [StrategyPublic.model_validate(s) for s in result.scalars().all()]

    async def get_by_code(self, code: str) -> StrategyPublic:
        result = await self.db.execute(select(Strategy).where(Strategy.code == code))
        s = result.scalar_one_or_none()
        if s is None:
            raise StrategyNotFoundError()
        return StrategyPublic.model_validate(s)

    # ---- Instances -------------------------------------------------------

    async def _get_strategy_by_code(self, code: str) -> Strategy:
        result = await self.db.execute(select(Strategy).where(Strategy.code == code))
        s = result.scalar_one_or_none()
        if s is None:
            raise StrategyNotFoundError()
        return s

    async def _own_broker(self, user_id: UUID, broker_account_id: UUID) -> BrokerAccount:
        result = await self.db.execute(
            select(BrokerAccount).where(
                BrokerAccount.id == broker_account_id,
                BrokerAccount.user_id == user_id,
                BrokerAccount.deleted_at.is_(None),
            )
        )
        ba = result.scalar_one_or_none()
        if ba is None:
            raise NotFoundError(
                "Broker account not found", code="BROKER_ACCOUNT_NOT_FOUND", status_code=404
            )
        return ba

    async def create_instance(
        self, user_id: UUID, payload: StrategyInstanceCreateRequest
    ) -> StrategyInstancePublic:
        strategy = await self._get_strategy_by_code(payload.strategy_code)
        await self._own_broker(user_id, payload.broker_account_id)

        # R5: tv_signal — pre-validate params + warn if TV is disabled.
        # We *create* the instance regardless (so the user can still configure
        # it ahead of an outage), but log a structured warning so support sees
        # it. live-gate will block actual go-live while TV is down.
        if strategy.code in TV_STRATEGY_CODES:
            self._validate_tv_signal_params(payload.params or {})
            settings = get_settings()
            if not getattr(settings, "tv_enabled", True):
                logger.warning(
                    "tv_signal_created_with_tv_disabled",
                    user_id=str(user_id),
                    strategy_code=strategy.code,
                )

        instance = StrategyInstance(
            user_id=user_id,
            broker_account_id=payload.broker_account_id,
            strategy_id=strategy.id,
            label=payload.label,
            params=payload.params or {},
            status=payload.mode,  # 'paper' or 'live'
            risk_percent=payload.risk_percent,
            max_daily_loss_cents=payload.max_daily_loss_cents,
        )
        self.db.add(instance)
        await self.db.flush()

        await record_audit(
            self.db,
            action="strategy_instance.created",
            actor_user_id=user_id,
            target_type="strategy_instance",
            target_id=instance.id,
            payload={"strategy": strategy.code, "mode": payload.mode, "label": payload.label},
        )
        await self.db.commit()
        await self.db.refresh(instance)
        return StrategyInstancePublic.model_validate(instance)

    @staticmethod
    def _validate_tv_signal_params(params: dict) -> None:
        """Validate tv_signal-specific params at create-time.

        Rules:
          - `intervals` must be a non-empty list and every value must be in
            SUPPORTED_TV_INTERVALS.
          - `score_threshold` (if present) must be 0–100.
          - `long_threshold` / `short_threshold` (if present) in [-1.0, 1.0]
            (Kairos's scorer normalizes to that range).
          - `confidence_min` (if present) in [0.0, 1.0].
        Raises ValidationFailedError on first offence.
        """
        intervals = params.get("intervals")
        if intervals is not None:
            if not isinstance(intervals, list) or not intervals:
                raise ValidationFailedError(
                    "tv_signal.intervals must be a non-empty list.",
                    details={"field": "params.intervals"},
                )
            bad = [i for i in intervals if i not in SUPPORTED_TV_INTERVALS]
            if bad:
                raise ValidationFailedError(
                    "tv_signal.intervals contains unsupported values.",
                    details={
                        "bad_intervals": bad,
                        "supported": sorted(SUPPORTED_TV_INTERVALS),
                    },
                )

        for key, lo, hi in [
            ("score_threshold", 0, 100),
            ("long_threshold", -1.0, 1.0),
            ("short_threshold", -1.0, 1.0),
            ("confidence_min", 0.0, 1.0),
        ]:
            if key in params and params[key] is not None:
                try:
                    val = float(params[key])
                except (TypeError, ValueError) as exc:
                    raise ValidationFailedError(
                        f"tv_signal.{key} must be numeric.",
                        details={"field": f"params.{key}"},
                    ) from exc
                if val < lo or val > hi:
                    raise ValidationFailedError(
                        f"tv_signal.{key} out of range [{lo}, {hi}].",
                        details={"field": f"params.{key}", "value": val},
                    )

    async def list_instances(self, user_id: UUID) -> list[StrategyInstancePublic]:
        result = await self.db.execute(
            select(StrategyInstance)
            .where(
                StrategyInstance.user_id == user_id,
                StrategyInstance.deleted_at.is_(None),
            )
            .order_by(StrategyInstance.created_at.desc())
        )
        return [
            StrategyInstancePublic.model_validate(i) for i in result.scalars().all()
        ]

    async def _own_instance(self, user_id: UUID, instance_id: UUID) -> StrategyInstance:
        result = await self.db.execute(
            select(StrategyInstance).where(
                StrategyInstance.id == instance_id,
                StrategyInstance.user_id == user_id,
                StrategyInstance.deleted_at.is_(None),
            )
        )
        i = result.scalar_one_or_none()
        if i is None:
            raise NotFoundError(
                "Strategy instance not found",
                code="STRATEGY_INSTANCE_NOT_FOUND",
                status_code=404,
            )
        return i

    async def update_instance(
        self,
        user_id: UUID,
        instance_id: UUID,
        payload: StrategyInstanceUpdateRequest,
    ) -> StrategyInstancePublic:
        instance = await self._own_instance(user_id, instance_id)
        if instance.status == "killed":
            raise StrategyInstanceConflictError("Instance is killed and immutable.")

        # If live, block high-risk param changes — revert first.
        if instance.status == "live":
            changed = {
                k: v
                for k, v in payload.model_dump(exclude_unset=True).items()
                if v is not None and k in HIGH_RISK_PARAM_KEYS
            }
            if changed:
                raise StrategyInstanceLockedError(
                    "Revert-to-paper before changing risk/params on a live instance.",
                    details={"locked_fields": sorted(changed.keys())},
                )

        if payload.label is not None:
            instance.label = payload.label
        if payload.params is not None:
            instance.params = payload.params
        if payload.risk_percent is not None:
            instance.risk_percent = payload.risk_percent
        if payload.max_daily_loss_cents is not None:
            instance.max_daily_loss_cents = payload.max_daily_loss_cents
        await self.db.commit()
        await self.db.refresh(instance)
        return StrategyInstancePublic.model_validate(instance)

    # ---- Live transitions ------------------------------------------------

    async def go_live(self, user: User, instance_id: UUID) -> tuple[GateResult, StrategyInstance]:
        """Run the gate. If pass → flip status=live and dispatch to OMS."""
        instance = await self._own_instance(user.id, instance_id)
        if instance.status == "live":
            from app.services.live_gate_service import LiveGateService

            gate = await LiveGateService(self.db).can_go_live(instance_id, user)
            return gate, instance
        if instance.status == "killed":
            raise StrategyInstanceConflictError("Killed instance cannot go live.")

        from app.services.live_gate_service import LiveGateService

        gate = await LiveGateService(self.db).can_go_live(instance_id, user)
        if not gate.passed:
            raise LiveGateFailedError(
                "Live gate checks failed.",
                details={"failed_checks": [c.model_dump() for c in gate.failed_checks]},
            )

        # Dispatch to OMS (best-effort; failure rolls back local flip)
        from app.services.oms_client import OMSClient

        oms = OMSClient()
        try:
            await oms.start_live(
                strategy_instance_id=instance.id,
                broker_account_id=instance.broker_account_id,
                params=instance.params,
                risk_limits={
                    "risk_percent": str(instance.risk_percent),
                    "max_daily_loss_cents": instance.max_daily_loss_cents,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("oms_start_failed", instance_id=str(instance.id), err=str(exc))
            raise StrategyInstanceConflictError(
                "OMS rejected go-live.", details={"reason": str(exc)}
            ) from exc

        instance.status = "live"
        instance.live_started_at = datetime.now(UTC)
        instance.started_at = instance.started_at or datetime.now(UTC)
        instance.stopped_at = None
        await record_audit(
            self.db,
            action="strategy_instance.go_live",
            actor_user_id=user.id,
            target_type="strategy_instance",
            target_id=instance.id,
            payload={"strategy_id": str(instance.strategy_id)},
        )
        await self.db.commit()
        await self.db.refresh(instance)
        return gate, instance

    async def revert_to_paper(
        self, user_id: UUID, instance_id: UUID
    ) -> StrategyInstancePublic:
        instance = await self._own_instance(user_id, instance_id)
        if instance.status != "live":
            return StrategyInstancePublic.model_validate(instance)

        # Close positions via OMS first; then flip locally.
        from app.services.oms_client import OMSClient

        oms = OMSClient()
        try:
            await oms.stop_live(strategy_instance_id=instance.id, close_positions=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "oms_stop_failed_continuing_local_flip",
                instance_id=str(instance.id),
                err=str(exc),
            )

        instance.status = "paper"
        await record_audit(
            self.db,
            action="strategy_instance.revert_to_paper",
            actor_user_id=user_id,
            target_type="strategy_instance",
            target_id=instance.id,
        )
        await self.db.commit()
        await self.db.refresh(instance)
        return StrategyInstancePublic.model_validate(instance)

    async def _strategy_code_for(self, instance: StrategyInstance) -> str | None:
        """Best-effort strategy_code lookup for audit log enrichment (R5)."""
        try:
            row = await self.db.execute(
                select(Strategy.code).where(Strategy.id == instance.strategy_id)
            )
            return row.scalar_one_or_none()
        except Exception:  # noqa: BLE001 — audit must never fail the txn
            return None

    async def start_instance(
        self, user_id: UUID, instance_id: UUID
    ) -> StrategyInstancePublic:
        instance = await self._own_instance(user_id, instance_id)
        if instance.status == "killed":
            raise StrategyInstanceConflictError("Killed instance cannot start.")
        if instance.status in ("paper", "live"):
            return StrategyInstancePublic.model_validate(instance)

        # MVP: paper-mode only (mode set at creation). Reactivate via 'paper'.
        instance.status = "paper"
        instance.started_at = datetime.now(UTC)
        instance.stopped_at = None
        strategy_code = await self._strategy_code_for(instance)
        await record_audit(
            self.db,
            action="strategy_instance.started",
            actor_user_id=user_id,
            target_type="strategy_instance",
            target_id=instance.id,
            payload={"strategy": strategy_code} if strategy_code else None,
        )
        await self.db.commit()
        await self.db.refresh(instance)
        return StrategyInstancePublic.model_validate(instance)

    async def stop_instance(
        self, user_id: UUID, instance_id: UUID
    ) -> StrategyInstancePublic:
        instance = await self._own_instance(user_id, instance_id)
        if instance.status == "killed":
            raise StrategyInstanceConflictError("Killed instance cannot stop.")
        instance.status = "stopped"
        instance.stopped_at = datetime.now(UTC)
        strategy_code = await self._strategy_code_for(instance)
        await record_audit(
            self.db,
            action="strategy_instance.stopped",
            actor_user_id=user_id,
            target_type="strategy_instance",
            target_id=instance.id,
            payload={"strategy": strategy_code} if strategy_code else None,
        )
        await self.db.commit()
        await self.db.refresh(instance)
        return StrategyInstancePublic.model_validate(instance)

    async def kill_instance(
        self, user_id: UUID, instance_id: UUID
    ) -> StrategyInstancePublic:
        instance = await self._own_instance(user_id, instance_id)
        instance.status = "killed"
        instance.kill_switch_armed = False
        instance.stopped_at = datetime.now(UTC)
        strategy_code = await self._strategy_code_for(instance)
        payload: dict = {"reason": "user_emergency_stop"}
        if strategy_code:
            payload["strategy"] = strategy_code
        await record_audit(
            self.db,
            action="strategy_instance.killed",
            actor_user_id=user_id,
            target_type="strategy_instance",
            target_id=instance.id,
            payload=payload,
        )
        await self.db.commit()
        await self.db.refresh(instance)
        return StrategyInstancePublic.model_validate(instance)

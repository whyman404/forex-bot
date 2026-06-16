"""Live-trading preflight gate.

Atlas Goro — eight checks must ALL pass before a user can flip a strategy
instance from paper to live. Failure returns a structured GateResult so the
UI can show exactly which check needs attention.

Checks:
  1. email_verified_at IS NOT NULL
  2. TOTP enabled (user.totp_secret IS NOT NULL)
  3. Active *paid* subscription (not just trialing)
  4. ≥1 completed backtest for this strategy with PF>1.3 AND MaxDD<25%
  5. ≥14 days of paper trading on this instance with ≥10 trades
  6. Signed live-trading agreement for this strategy code (live_consents)
  7. Broker account ≥ min size ($500 forex / $200 crypto)
  8. User-global kill switch NOT armed (no killed instances within 24h)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.backtest import Backtest
from app.models.broker_account import BrokerAccount
from app.models.live_consent import LiveConsent
from app.models.strategy import Strategy
from app.models.strategy_instance import StrategyInstance
from app.models.trade import Trade
from app.models.user import User
from app.schemas.live import GateCheck, GateResult
from app.services.subscription_guard import is_paid_user

logger = get_logger(__name__)


class LiveGateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def can_go_live(self, instance_id: UUID, user: User) -> GateResult:
        """Run all checks. Returns aggregated GateResult.

        Never raises for failing checks (returns structured info instead);
        only raises NotFoundError if instance/strategy missing.
        """
        # Load instance + strategy + broker
        result = await self.db.execute(
            select(StrategyInstance).where(
                StrategyInstance.id == instance_id,
                StrategyInstance.user_id == user.id,
                StrategyInstance.deleted_at.is_(None),
            )
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            raise NotFoundError(
                "Strategy instance not found",
                code="STRATEGY_INSTANCE_NOT_FOUND",
            )

        strategy = (
            await self.db.execute(
                select(Strategy).where(Strategy.id == instance.strategy_id)
            )
        ).scalar_one_or_none()
        if strategy is None:
            raise NotFoundError("Strategy missing", code="STRATEGY_NOT_FOUND")

        broker = (
            await self.db.execute(
                select(BrokerAccount).where(
                    BrokerAccount.id == instance.broker_account_id,
                    BrokerAccount.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        checks: list[GateCheck] = []

        # 1) Email verified
        checks.append(
            GateCheck(
                name="email_verified",
                passed=user.email_verified_at is not None,
                detail=None if user.email_verified_at else "Verify your email first.",
            )
        )

        # 2) TOTP
        checks.append(
            GateCheck(
                name="totp_enabled",
                passed=user.totp_secret is not None,
                detail=None if user.totp_secret else "Enable 2FA (TOTP) first.",
            )
        )

        # 3) Active paid subscription
        paid = await is_paid_user(self.db, user.id)
        checks.append(
            GateCheck(
                name="active_paid_subscription",
                passed=paid,
                detail=None if paid else "Active paid plan required for live trading.",
            )
        )

        # 4) Qualifying backtest
        bt_ok, bt_detail = await self._has_qualifying_backtest(user.id, strategy.id)
        checks.append(
            GateCheck(name="qualifying_backtest", passed=bt_ok, detail=bt_detail)
        )

        # 5) Paper trading track record
        paper_ok, paper_detail = await self._has_paper_track_record(instance)
        checks.append(
            GateCheck(name="paper_track_record", passed=paper_ok, detail=paper_detail)
        )

        # 6) Live consent
        consent_ok = await self._has_live_consent(user.id, strategy.code)
        checks.append(
            GateCheck(
                name="live_consent_signed",
                passed=consent_ok,
                detail=None
                if consent_ok
                else f"Sign live-trading agreement for {strategy.code}.",
            )
        )

        # 7) Broker account size
        bal_ok, bal_detail = self._check_broker_balance(broker, strategy.asset_class)
        checks.append(
            GateCheck(name="broker_min_balance", passed=bal_ok, detail=bal_detail)
        )

        # 8) Kill switch global state
        ks_ok, ks_detail = await self._global_kill_switch_clear(user.id)
        checks.append(
            GateCheck(name="kill_switch_clear", passed=ks_ok, detail=ks_detail)
        )

        failed = [c for c in checks if not c.passed]
        return GateResult(
            passed=len(failed) == 0,
            failed_checks=failed,
            warnings=[],
            checks=checks,
        )

    # ---- individual checks ----------------------------------------------

    async def _has_qualifying_backtest(
        self, user_id: UUID, strategy_id: UUID
    ) -> tuple[bool, str | None]:
        min_pf = Decimal(str(self.settings.live_min_profit_factor))
        max_dd = Decimal(str(self.settings.live_max_drawdown_pct))
        result = await self.db.execute(
            select(func.count(Backtest.id)).where(
                Backtest.user_id == user_id,
                Backtest.strategy_id == strategy_id,
                Backtest.status == "completed",
                Backtest.profit_factor.isnot(None),
                Backtest.profit_factor > min_pf,
                Backtest.max_drawdown_pct.isnot(None),
                Backtest.max_drawdown_pct < max_dd,
            )
        )
        n = int(result.scalar_one() or 0)
        if n == 0:
            return False, (
                f"Need ≥1 completed backtest with profit_factor > {min_pf} "
                f"and max_drawdown_pct < {max_dd}."
            )
        return True, None

    async def _has_paper_track_record(
        self, instance: StrategyInstance
    ) -> tuple[bool, str | None]:
        min_days = self.settings.live_min_paper_days
        min_trades = self.settings.live_min_paper_trades

        started = instance.started_at or instance.created_at
        if started is None:
            return False, "Instance has not started paper trading."
        elapsed_days = (datetime.now(UTC) - started).days
        if elapsed_days < min_days:
            return False, f"Paper traded {elapsed_days}/{min_days} days."

        result = await self.db.execute(
            select(func.count()).select_from(Trade).where(
                Trade.strategy_instance_id == instance.id
            )
        )
        n = int(result.scalar_one() or 0)
        if n < min_trades:
            return False, f"Paper trades {n}/{min_trades}."
        return True, None

    async def _has_live_consent(self, user_id: UUID, strategy_code: str) -> bool:
        result = await self.db.execute(
            select(func.count()).select_from(LiveConsent).where(
                LiveConsent.user_id == user_id,
                LiveConsent.strategy_code == strategy_code,
                LiveConsent.risk_acknowledged.is_(True),
            )
        )
        return int(result.scalar_one() or 0) > 0

    def _check_broker_balance(
        self, broker: BrokerAccount | None, asset_class: str
    ) -> tuple[bool, str | None]:
        if broker is None:
            return False, "Broker account not found."
        # asset_class: 'gold' → forex; 'btc' → crypto
        if asset_class == "btc":
            min_cents = self.settings.live_min_account_size_crypto_cents
        else:
            min_cents = self.settings.live_min_account_size_forex_cents

        if broker.balance_cached_cents is None:
            return False, "Broker balance unknown — run /test-connection first."
        if broker.balance_cached_cents < min_cents:
            return False, (
                f"Broker balance ${broker.balance_cached_cents/100:.2f} < "
                f"required ${min_cents/100:.2f}."
            )
        return True, None

    async def _global_kill_switch_clear(self, user_id: UUID) -> tuple[bool, str | None]:
        since = datetime.now(UTC) - timedelta(hours=24)
        result = await self.db.execute(
            select(func.count(StrategyInstance.id)).where(
                StrategyInstance.user_id == user_id,
                StrategyInstance.status == "killed",
                StrategyInstance.stopped_at.isnot(None),
                StrategyInstance.stopped_at >= since,
            )
        )
        recent_kills = int(result.scalar_one() or 0)
        if recent_kills > 0:
            return False, (
                f"Cooldown active — {recent_kills} instance(s) killed in last 24h."
            )
        return True, None

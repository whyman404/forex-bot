"""LiveEngine specialization that queries TradingView at each bar close.

Differences vs the vanilla `LiveEngine`:
    - Constructs (and re-uses) a `TVClient` + `Scorer` once at start.
    - Injects them into the `TVSignalStrategy` instance.
    - Adds TV-specific health snippets to the heartbeat payload.

Everything else (risk gate, OMS, MT5 bridge calls, circuit breakers,
HMAC to backend) is INHERITED unchanged from `LiveEngine`. The whole
point of TradingView integration is to replace the SIGNAL SOURCE — not
to change how trades are placed or risked.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from live.engine import EngineSpec, EngineStatus, LiveEngine

logger = logging.getLogger(__name__)


class TVSignalLiveEngine(LiveEngine):
    """Live engine driven by TradingView multi-TF signals."""

    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        # Lazy — only construct when TV is enabled. If not enabled, the
        # engine still starts but signals are skipped (logged warning).
        self._tv_client = None
        self._tv_scorer = None
        self._tv_fatal_at: float | None = None
        self._init_tv()

    # ------------------------------------------------------------------
    def _init_tv(self) -> None:
        try:
            from tradingview.client import TVClient, tv_enabled, tv_unavailable_reason
            from tradingview.scorer import Scorer

            if not tv_enabled():
                logger.warning(
                    "tv_signal_engine.tv_disabled reason=%s",
                    tv_unavailable_reason(),
                )
                return
            self._tv_client = TVClient()
            self._tv_scorer = Scorer()
            logger.info("tv_signal_engine.tv_ready")
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("tv_signal_engine.init_failed err=%s", str(e)[:200])

    # ------------------------------------------------------------------
    def _make_strategy(self):
        """Override — inject TV client into the strategy."""
        strat = super()._make_strategy()
        # Only inject if TV is up; otherwise strategy degrades to proxy path
        # (which is undesirable in live, so we'll also halt below).
        if self._tv_client is not None and hasattr(strat, "set_tv_client"):
            strat.set_tv_client(self._tv_client, self._tv_scorer)
        return strat

    # ------------------------------------------------------------------
    def _on_new_bar(self) -> None:
        """Override to halt cleanly when TV is unavailable.

        Per Kairos's identity: if the signal source is dead, we DON'T
        trade blindly — we halt and let the operator decide.
        """
        if self._tv_client is None:
            # Halt instead of trading on stale or zero data.
            if self._tv_fatal_at is None:
                self._tv_fatal_at = time.time()
            if self.runtime.status != EngineStatus.HALTED:
                self.runtime.status = EngineStatus.HALTED
                self.internal.emit_health(
                    self.spec.strategy_instance_id,
                    "halted",
                    {"reason": "tv_signal_source_unavailable"},
                )
            return
        # Normal path — delegate to parent.
        super()._on_new_bar()

    # ------------------------------------------------------------------
    def status_snapshot(self) -> dict[str, Any]:
        snap = super().status_snapshot()
        snap["tv"] = {
            "enabled": self._tv_client is not None,
            "throttle_concurrent": int(os.getenv("TV_THROTTLE_CONCURRENT", "4")),
            "throttle_spacing_sec": float(os.getenv("TV_THROTTLE_SPACING_SEC", "0.8")),
            "cache_ttl_sec": float(os.getenv("TV_CACHE_TTL_SEC", "60")),
            "fatal_since": self._tv_fatal_at,
        }
        return snap

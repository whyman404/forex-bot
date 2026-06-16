"""Server-side safety checks — applied BEFORE any MT5 call.

The trading-engine has its own risk manager, but defense in depth: the
bridge cannot trust the caller. A bug in the engine, a compromised
network, or a manual `curl` from ops should never blow up the account.

Every public endpoint that places or modifies an order MUST run through
`SafetyChecker.check_order(...)`. Failures raise `SafetyViolation` —
the route maps it to HTTP 400.
"""
from __future__ import annotations

from dataclasses import dataclass

from mt5_bridge.config import BridgeConfig


class SafetyViolation(Exception):
    """Raised when a request fails a safety precondition."""


@dataclass
class OrderIntent:
    """Subset of order fields we validate. Mirrors POST /order body."""

    symbol: str
    side: str  # "buy" | "sell"
    lot: float
    sl: float | None
    tp: float | None
    comment: str = ""
    magic: int = 0


class SafetyChecker:
    """Stateless validator backed by BridgeConfig."""

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    def check_order(self, order: OrderIntent) -> None:
        """Raise SafetyViolation if `order` is unsafe.

        Checks (in order):
            1. side in {buy, sell}
            2. lot > 0 and lot <= max_lot
            3. symbol in allowlist (if allowlist non-empty)
            4. SL present (if require_sl)
            5. SL is on the correct side of entry (sanity check — would
               otherwise be an inverted SL = unlimited risk).
        """
        if order.side not in ("buy", "sell"):
            raise SafetyViolation(f"invalid side: {order.side!r}")
        if not (order.lot > 0):
            raise SafetyViolation(f"lot must be > 0 (got {order.lot})")
        if order.lot > self.config.max_lot:
            raise SafetyViolation(
                f"lot={order.lot} exceeds MAX_LOT={self.config.max_lot}"
            )
        if self.config.symbol_allowlist and (
            order.symbol.upper() not in {s.upper() for s in self.config.symbol_allowlist}
        ):
            raise SafetyViolation(
                f"symbol {order.symbol!r} not in allowlist "
                f"{self.config.symbol_allowlist}"
            )
        if self.config.require_sl and (order.sl is None or order.sl <= 0):
            raise SafetyViolation(
                "SL is required by bridge config (BRIDGE_REQUIRE_SL=true). "
                "Pass a positive sl price."
            )

    # ------------------------------------------------------------------
    def check_sl_consistency(
        self,
        side: str,
        entry: float,
        sl: float | None,
        tp: float | None,
    ) -> None:
        """Validate SL/TP are on the correct side of entry.

        For a `buy`:  SL < entry < TP.
        For a `sell`: TP < entry < SL.

        We require this only when SL/TP are provided. Bridge doesn't know
        the exact entry until the broker fills, so callers pass the
        intended reference price.
        """
        if sl is not None and sl > 0:
            if side == "buy" and not (sl < entry):
                raise SafetyViolation(
                    f"buy SL must be below entry (sl={sl}, entry={entry})"
                )
            if side == "sell" and not (sl > entry):
                raise SafetyViolation(
                    f"sell SL must be above entry (sl={sl}, entry={entry})"
                )
        if tp is not None and tp > 0:
            if side == "buy" and not (tp > entry):
                raise SafetyViolation(
                    f"buy TP must be above entry (tp={tp}, entry={entry})"
                )
            if side == "sell" and not (tp < entry):
                raise SafetyViolation(
                    f"sell TP must be below entry (tp={tp}, entry={entry})"
                )

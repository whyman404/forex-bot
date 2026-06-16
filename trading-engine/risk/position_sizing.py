"""Position sizing helpers.

All sizing functions return a *position size* in the broker's unit (lots for
MT5, contracts for crypto). Caller is responsible for rounding to broker
min-lot / step-size — see `data.symbols`.

Master rule we never violate:
    risk_per_trade ≤ 2% of account equity (default 1%).
    risk_per_day   ≤ 5% of account equity.
    max DD circuit ≤ 15% (auto-disable strategy).

Kelly is capped at 0.25× full Kelly because:
    * Edge estimates have huge variance,
    * Full Kelly survives only with TRUE edge, not estimated edge.
"""
from __future__ import annotations

import math


def _safe_div(a: float, b: float) -> float:
    return a / b if b != 0 else 0.0


def fixed_fractional(
    account_equity: float,
    risk_pct: float,
    sl_distance: float,
    pip_value_per_unit: float = 1.0,
) -> float:
    """Classic fixed-fractional sizing.

    Args:
        account_equity: current balance / equity.
        risk_pct: percentage of equity to risk on this trade (e.g. 1.0 for 1%).
        sl_distance: distance from entry to SL in PRICE terms (not pips).
        pip_value_per_unit: how much PRICE one position-unit corresponds to
            (1.0 for crypto USD-quoted; for forex/gold use contract spec).

    Returns:
        Position size in units (broker's unit).
    """
    if account_equity <= 0 or risk_pct <= 0 or sl_distance <= 0:
        return 0.0
    risk_amount = account_equity * (risk_pct / 100.0)
    return _safe_div(risk_amount, sl_distance * pip_value_per_unit)


def atr_position_size(
    account_equity: float,
    risk_pct: float,
    atr: float,
    atr_mult: float = 1.5,
    pip_value_per_unit: float = 1.0,
) -> float:
    """ATR-based sizing — SL distance = atr × atr_mult."""
    sl_distance = atr * atr_mult
    return fixed_fractional(account_equity, risk_pct, sl_distance, pip_value_per_unit)


def volatility_target(
    account_equity: float,
    target_vol_pct: float,
    realized_vol_pct: float,
    notional_per_unit: float,
) -> float:
    """Scale position so portfolio volatility ≈ target.

    Args:
        target_vol_pct: e.g. 15.0 for 15% annualized.
        realized_vol_pct: instrument's recent annualized vol in pct.
        notional_per_unit: USD notional one position-unit represents.
    """
    if realized_vol_pct <= 0 or notional_per_unit <= 0:
        return 0.0
    target_notional = account_equity * (target_vol_pct / realized_vol_pct)
    return target_notional / notional_per_unit


def kelly_fractional(
    win_rate: float,
    avg_win_r: float,
    avg_loss_r: float,
    cap: float = 0.25,
) -> float:
    """Fractional Kelly. Always capped (default 25%).

    f* = (W / A) - ((1 - W) / B)
        where W = win prob, A = avg loss in R, B = avg win in R.

    We cap and floor at zero (never short the strategy by going negative).
    """
    if avg_win_r <= 0 or avg_loss_r <= 0:
        return 0.0
    w = max(0.0, min(1.0, win_rate))
    full = (w / avg_loss_r) - ((1 - w) / avg_win_r)
    full = max(0.0, full)
    return min(full * cap, cap)


def round_to_step(size: float, step: float, min_size: float = 0.0) -> float:
    """Round position size down to broker's lot step."""
    if step <= 0:
        return max(size, min_size)
    rounded = math.floor(size / step) * step
    return max(rounded, min_size)

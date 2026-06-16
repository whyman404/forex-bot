"""Live monitoring — per-engine health + today's PnL.

The endpoint is consumed by Atlas (backend) to render the live dashboard
and to trigger ops alerts. We surface:
    - engine status (running/halted/killed)
    - circuit breaker state
    - today's realized PnL
    - count of open positions tagged by our magic
    - last heartbeat age
"""
from __future__ import annotations

import time
from typing import Any

from live import router


def engine_health(strategy_instance_id: str) -> dict[str, Any]:
    snap = router.status(strategy_instance_id)
    if snap is None:
        return {
            "strategy_instance_id": strategy_instance_id,
            "found": False,
        }
    last_hb = snap["runtime"].get("last_heartbeat_at") or 0
    age = (time.time() - last_hb) if last_hb else None
    return {
        "strategy_instance_id": strategy_instance_id,
        "found": True,
        "status": snap["status"],
        "today_pnl": snap["breaker"]["realized_pnl_today"],
        "drawdown_pct": snap["breaker"]["drawdown_pct"],
        "killed": snap["breaker"]["killed"],
        "halted": snap["breaker"]["halted"],
        "halt_reason": snap["breaker"]["reason"],
        "open_position_ticket": snap["runtime"].get("open_position_ticket"),
        "signals_today": snap["runtime"].get("signals_today", 0),
        "fills_today": snap["runtime"].get("fills_today", 0),
        "heartbeat_age_sec": age,
    }

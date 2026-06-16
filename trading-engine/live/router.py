"""Engine router — registry of LiveEngine instances keyed by strategy_instance_id.

Atlas calls /live/start with a spec; we instantiate a LiveEngine and stash
it in `_REGISTRY`. /live/stop, /live/kill, /live/{id}/status look it up.

Why an in-process registry?
- Phase 2 still runs the trading-engine as a single process per Render
  service. The /live/* endpoints share state via this dict.
- Phase 3 will move to a per-strategy worker pool + Redis state — but the
  request shape Atlas uses does not change.
"""
from __future__ import annotations

import threading
from typing import Any

from live.engine import EngineSpec, LiveEngine

_LOCK = threading.RLock()
_REGISTRY: dict[str, LiveEngine] = {}


def start(spec: EngineSpec) -> dict[str, Any]:
    """Idempotent — starting an already-running id returns its current status."""
    with _LOCK:
        existing = _REGISTRY.get(spec.strategy_instance_id)
        if existing and existing.runtime.status.value in ("running", "starting", "halted"):
            return {"ok": True, "status": existing.runtime.status.value, "existing": True}
        engine = LiveEngine(spec)
        res = engine.on_start()
        _REGISTRY[spec.strategy_instance_id] = engine
        return res


def stop(strategy_instance_id: str) -> dict[str, Any]:
    with _LOCK:
        engine = _REGISTRY.get(strategy_instance_id)
        if not engine:
            return {"ok": False, "reason": "not_found"}
        return engine.on_stop()


def kill(strategy_instance_id: str) -> dict[str, Any]:
    with _LOCK:
        engine = _REGISTRY.get(strategy_instance_id)
        if not engine:
            return {"ok": False, "reason": "not_found"}
        return engine.on_kill()


def status(strategy_instance_id: str) -> dict[str, Any] | None:
    with _LOCK:
        engine = _REGISTRY.get(strategy_instance_id)
        return engine.status_snapshot() if engine else None


def all_status() -> list[dict[str, Any]]:
    with _LOCK:
        return [e.status_snapshot() for e in _REGISTRY.values()]


def _reset_for_tests() -> None:  # pragma: no cover — used by pytest fixtures
    with _LOCK:
        for e in _REGISTRY.values():
            try:
                e.on_stop()
            except Exception:
                pass
        _REGISTRY.clear()

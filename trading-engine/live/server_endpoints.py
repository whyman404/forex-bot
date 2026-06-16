"""Adds /live/* endpoints to the FastAPI app.

Wire from `trading-engine/server.py`:

    from live.server_endpoints import register_live_routes
    register_live_routes(app)
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from live import router
from live.engine import EngineSpec
from live.gate import evaluate_live_gate
from live.monitor import engine_health


class StartLiveRequest(BaseModel):
    strategy_instance_id: str
    strategy_code: str
    broker_account_id: str
    bridge_url: str
    bridge_token: str
    mt5_server: str
    mt5_login: int
    mt5_password: str
    symbol: str
    timeframe: str
    magic: int
    params: dict[str, Any] = Field(default_factory=dict)
    risk_limits: dict[str, Any] = Field(default_factory=dict)
    breaker_limits: dict[str, Any] = Field(default_factory=dict)
    lot_step: float = 0.01
    min_lot: float = 0.01
    pip_value_per_unit: float = 1.0


class StopLiveRequest(BaseModel):
    strategy_instance_id: str


def register_live_routes(app: FastAPI) -> None:
    @app.post("/live/start", status_code=202)
    def live_start(req: StartLiveRequest) -> dict[str, Any]:
        spec = EngineSpec(**req.model_dump())
        result = router.start(spec)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        return result

    @app.post("/live/stop", status_code=202)
    def live_stop(req: StopLiveRequest) -> dict[str, Any]:
        result = router.stop(req.strategy_instance_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result)
        return result

    @app.post("/live/kill", status_code=202)
    def live_kill(req: StopLiveRequest) -> dict[str, Any]:
        result = router.kill(req.strategy_instance_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result)
        return result

    @app.get("/live/{strategy_instance_id}/status")
    def live_status(strategy_instance_id: str) -> dict[str, Any]:
        snap = router.status(strategy_instance_id)
        if snap is None:
            raise HTTPException(status_code=404, detail="not_found")
        return snap

    @app.get("/live/{strategy_instance_id}/health")
    def live_health(strategy_instance_id: str) -> dict[str, Any]:
        return engine_health(strategy_instance_id)

    @app.get("/live/{strategy_instance_id}/gate")
    def live_gate(strategy_instance_id: str) -> dict[str, Any]:
        return evaluate_live_gate(strategy_instance_id).to_dict()

    @app.get("/live")
    def live_list() -> dict[str, Any]:
        return {"engines": router.all_status()}

"""HTTP routers — one file per resource. Mounted in app/main.py."""

from fastapi import APIRouter

from app.api import (
    admin,
    auth,
    backtests,
    billing,
    broker_accounts,
    compliance,
    internal,
    live_consents,
    notifications,
    strategies,
    strategy_instances,
    tradingview,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(broker_accounts.router, prefix="/broker-accounts", tags=["broker"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategy"])
api_router.include_router(
    strategy_instances.router, prefix="/strategy-instances", tags=["strategy-instance"]
)
api_router.include_router(backtests.router, prefix="/backtests", tags=["backtest"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(
    live_consents.router, prefix="/live-consents", tags=["live-consent"]
)
api_router.include_router(compliance.router, prefix="/users", tags=["compliance"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notification"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(internal.router, prefix="/internal", tags=["internal"])
api_router.include_router(tradingview.router, prefix="/tv", tags=["tradingview"])

__all__ = ["api_router"]

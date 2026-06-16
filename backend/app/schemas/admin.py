"""Admin schemas — Pydantic contracts for /api/v1/admin/*.

Atlas Goro — strict input validation, no leakage of secrets/PII in error paths.
Coordinates with Argus R4 (step-up TOTP) and Eos R6 (admin UI).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

Role = Literal["user", "admin"]
Channel = Literal["inapp", "email"]
Audience = Literal["all", "active", "user", "admin", "pro_monthly", "pro_yearly", "lifetime", "trial"]


# ---------------- Users ----------------


class UserAdminSummary(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    country: str
    role: Role
    created_at: datetime
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    is_banned: bool = False
    deleted_at: datetime | None = None
    subscription_status: str | None = None
    subscription_plan: str | None = None
    broker_count: int = Field(ge=0, default=0)
    strategy_instance_count: int = Field(ge=0, default=0)


class SubscriptionAdminMini(BaseModel):
    id: UUID
    plan: str
    status: str
    current_period_end: datetime | None = None


class BrokerAdminMini(BaseModel):
    id: UUID
    broker: str
    account_label: str
    is_active: bool
    last_sync_at: datetime | None = None


class StrategyInstanceAdminMini(BaseModel):
    id: UUID
    label: str
    status: str
    kill_switch_armed: bool
    started_at: datetime | None = None


class BacktestAdminMini(BaseModel):
    id: UUID
    status: str
    asset_symbol: str
    timeframe: str
    created_at: datetime


class ConsentAdminMini(BaseModel):
    kind: str
    accepted_at: datetime | None = None
    version: str | None = None


class UserAdminDetail(UserAdminSummary):
    subscriptions: list[SubscriptionAdminMini] = Field(default_factory=list)
    broker_accounts: list[BrokerAdminMini] = Field(default_factory=list)
    strategy_instances: list[StrategyInstanceAdminMini] = Field(default_factory=list)
    recent_backtests: list[BacktestAdminMini] = Field(default_factory=list)
    consents: list[ConsentAdminMini] = Field(default_factory=list)


class UserPatchAdmin(BaseModel):
    role: Role | None = None
    full_name: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    email_verified: bool | None = None
    is_banned: bool | None = None

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class ResetPasswordResponse(BaseModel):
    """Returned ONCE — plaintext never logged."""

    user_id: UUID
    temporary_password: str
    must_change_on_next_login: bool = True


class ImpersonationRequest(BaseModel):
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ImpersonationResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int = Field(ge=1, le=900)
    impersonated_user_id: UUID
    impersonator_id: UUID


# ---------------- Subscriptions ----------------


class GrantPlanRequest(BaseModel):
    plan_code: Literal["trial", "pro_monthly", "pro_yearly", "lifetime"]
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    reason: str = Field(min_length=1, max_length=500)


# ---------------- Audit log ----------------


class AuditLogEntry(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    target_type: str | None
    target_id: UUID | None
    payload_redacted: dict[str, Any]
    ip_addr: str | None
    user_agent: str | None
    created_at: datetime


# ---------------- Metrics + health ----------------


class AdminMetricsSnapshot(BaseModel):
    users_total: int = Field(ge=0)
    users_active_7d: int = Field(ge=0)
    users_new_7d: int = Field(ge=0)
    subs_active_count: int = Field(ge=0)
    mrr_estimate_cents: int = Field(ge=0)
    churn_30d_pct: float = Field(ge=0.0)
    backtests_today: int = Field(ge=0)
    signals_today: int = Field(ge=0)
    trades_today: int = Field(ge=0)
    gross_pnl_today_cents: int
    live_engines_running: int = Field(ge=0)
    kill_switches_armed: int = Field(ge=0)
    email_queue_depth: int = Field(ge=0)
    backtest_queue_depth: int = Field(ge=0)
    captured_at: datetime


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "fail", "not_configured", "unknown"]
    last_check: datetime
    detail: str | None = None
    latency_ms: float | None = None


class DependencyHealth(BaseModel):
    overall: Literal["ok", "degraded", "fail"]
    dependencies: list[DependencyStatus]


# ---------------- Strategies ----------------


class StrategyAdminPatch(BaseModel):
    is_enabled: bool | None = None
    risk_rating: Literal["low", "medium", "high"] | None = None
    default_params: dict[str, Any] | None = None


class KillAllResponse(BaseModel):
    strategy_code: str
    instances_killed: int = Field(ge=0)


# ---------------- Bridges ----------------


class Mt5BridgeStatus(BaseModel):
    id: UUID
    user_id: UUID
    broker: str
    account_label: str
    is_active: bool
    last_sync_at: datetime | None
    heartbeat_age_seconds: int | None
    status: Literal["ok", "stale", "down", "unknown"]


class ProbeResponse(BaseModel):
    bridge_id: UUID
    status: Literal["ok", "fail"]
    detail: str | None = None
    probed_at: datetime


# ---------------- Broadcast ----------------


class BroadcastRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)
    audience: Audience
    channel: Channel = "inapp"


class BroadcastResponse(BaseModel):
    queued_count: int = Field(ge=0)
    audience: Audience
    channel: Channel


# ---------------- Kill switch ----------------


class KillSwitchRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class KillSwitchStatus(BaseModel):
    engaged: bool
    engaged_at: datetime | None = None
    engaged_by: list[UUID] = Field(default_factory=list)
    reason: str | None = None
    approvers_required: int = 1
    approvers_collected: int = 0
    pending: bool = False

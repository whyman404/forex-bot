"""Internal endpoints — trading-engine (Kairos) → backend (Atlas).

Atlas Goro — auth is HMAC-SHA256 over a canonical string built from request
method, path, timestamp, nonce and SHA-256 of the raw body. The canonical
scheme matches `trading-engine/live/internal_client.py` exactly:

    canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{body_sha256}"
    sig       = hmac_sha256(INTERNAL_API_SECRET, canonical).hex()

    headers:
        X-Internal-Ts:    <unix-seconds>
        X-Internal-Nonce: <uuid4-hex>
        X-Internal-Sig:   <hex digest>

A legacy `X-Internal-Signature` (raw-body HMAC) is still accepted to keep
the Phase-1 mt5-bridge stub flowing. Once the engine fully ships the
canonical scheme we can drop the fallback.

We never log the secret. If verification fails we return 401 with a stable
code; on missing/invalid signature we DO NOT touch the DB.

These endpoints are excluded from the public OpenAPI (internal contract).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    ErrorResponse,
    InternalSignatureInvalidError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.models.signal import Signal
from app.models.strategy_instance import StrategyInstance
from app.models.trade import Trade
from app.models.user import User
from app.schemas.internal import (
    InternalAck,
    InternalHealth,
    InternalSignal,
    InternalTradeFill,
)
from app.schemas.live import StrategyInstanceHealth
from app.services.oms_client import verify_canonical, verify_signature

logger = get_logger(__name__)

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


def _client_in_allowlist(request: Request, allow_cidrs: list[str]) -> bool:
    """Best-effort source IP check against configured CIDRs.

    Used as DEFENSE-IN-DEPTH only — HMAC remains the primary control.
    On Railway, services share an internal `*.railway.internal` network and
    the operator can configure a private IP range. If the allowlist is
    empty we return True (no enforcement).
    """
    if not allow_cidrs:
        return True
    import ipaddress

    # Prefer X-Forwarded-For (Railway sets it); fall back to client.host.
    xff = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    raw_ip = xff or (request.client.host if request.client else "")
    if not raw_ip:
        return False
    try:
        ip = ipaddress.ip_address(raw_ip)
    except ValueError:
        return False
    for cidr in allow_cidrs:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


async def _verify_internal_sig(
    request: Request,
    x_internal_signature: str = Header(default="", alias="X-Internal-Signature"),
    x_internal_sig: str = Header(default="", alias="X-Internal-Sig"),
    x_internal_ts: str = Header(default="", alias="X-Internal-Ts"),
    x_internal_nonce: str = Header(default="", alias="X-Internal-Nonce"),
) -> bytes:
    """Read raw body, verify HMAC.

    Accepts EITHER the canonical scheme (preferred, replay-protected) OR the
    legacy single-header form. Returns raw body bytes for handlers to use.
    """
    settings = get_settings()
    secret = settings.internal_api_secret
    raw = await request.body()

    # Defense-in-depth: source IP allowlist (HMAC still primary).
    if not _client_in_allowlist(request, settings.internal_trusted_proxy_cidrs):
        logger.warning(
            "internal_caller_outside_allowlist",
            path=request.url.path,
            ip=(request.client.host if request.client else None),
        )
        # Don't raise here — let HMAC speak; this is signal-only for now.

    if not secret:
        # In dev with no secret configured, allow but warn loudly.
        logger.warning("internal_secret_unset_allowing_request")
        return raw

    # Preferred: canonical scheme used by the trading-engine InternalClient.
    if x_internal_sig and x_internal_ts and x_internal_nonce:
        if verify_canonical(
            secret,
            request.method,
            request.url.path,
            raw,
            x_internal_ts,
            x_internal_nonce,
            x_internal_sig,
        ):
            return raw
        raise InternalSignatureInvalidError()

    # Legacy fallback — raw-body HMAC, no replay protection.
    if x_internal_signature and verify_signature(secret, raw, x_internal_signature):
        return raw

    raise InternalSignatureInvalidError()


@router.post(
    "/signals",
    response_model=InternalAck,
    responses=ERROR_RESPONSES,
    include_in_schema=False,
    summary="[internal] Trading-engine pushes a generated signal",
)
async def internal_signal(
    payload: InternalSignal,
    _raw: bytes = Depends(_verify_internal_sig),
    db: AsyncSession = Depends(get_db),
) -> InternalAck:
    row = Signal(
        strategy_instance_id=payload.strategy_instance_id,
        ts=payload.ts,
        direction=payload.direction,
        price=payload.price,
        sl=payload.sl,
        tp=payload.tp,
        reason=payload.reason,
        status=payload.status,
        broker_order_id=payload.broker_order_id,
    )
    db.add(row)
    # Touch last_signal_at on the instance (best-effort)
    inst = await db.get(StrategyInstance, payload.strategy_instance_id)
    if inst is not None:
        inst.last_signal_at = payload.ts
    await db.commit()
    await db.refresh(row)
    return InternalAck(accepted=True, id=row.id)


@router.post(
    "/trades",
    response_model=InternalAck,
    responses=ERROR_RESPONSES,
    include_in_schema=False,
    summary="[internal] Trading-engine pushes a trade fill",
)
async def internal_trade(
    payload: InternalTradeFill,
    _raw: bytes = Depends(_verify_internal_sig),
    db: AsyncSession = Depends(get_db),
) -> InternalAck:
    row = Trade(
        strategy_instance_id=payload.strategy_instance_id,
        signal_id=payload.signal_id,
        broker_account_id=payload.broker_account_id,
        symbol=payload.symbol,
        side=payload.side,
        lot_size=payload.lot_size,
        entry_price=payload.entry_price,
        entry_at=payload.entry_at,
        exit_price=payload.exit_price,
        exit_at=payload.exit_at,
        sl=payload.sl,
        tp=payload.tp,
        commission_cents=payload.commission_cents,
        swap_cents=payload.swap_cents,
        gross_pnl_cents=payload.gross_pnl_cents,
        net_pnl_cents=payload.net_pnl_cents,
        status=payload.status,
        broker_ticket=payload.broker_ticket,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return InternalAck(accepted=True, id=row.id)


@router.post(
    "/health",
    response_model=InternalAck,
    responses=ERROR_RESPONSES,
    include_in_schema=False,
    summary="[internal] Heartbeat from trading-engine (every 30s)",
)
async def internal_health(
    payload: InternalHealth,
    _raw: bytes = Depends(_verify_internal_sig),
    db: AsyncSession = Depends(get_db),
) -> InternalAck:
    inst = await db.get(StrategyInstance, payload.strategy_instance_id)
    if inst is None:
        return InternalAck(accepted=False)
    # Cache snapshot fields on the instance (cheap to read for /health)
    inst.daily_loss_today_cents = payload.daily_loss_cents
    inst.kill_switch_armed = payload.kill_switch_armed
    inst.last_signal_at = payload.heartbeat_at or inst.last_signal_at
    await db.commit()
    return InternalAck(accepted=True, id=inst.id)


# ---------------------------------------------------------------------------
# Read-side helpers (NOT internal) — exposed under /strategy-instances/{id}/...
# ---------------------------------------------------------------------------

read_router = APIRouter()


@read_router.get(
    "/{instance_id}/health",
    response_model=StrategyInstanceHealth,
    summary="Current live health snapshot for a strategy instance",
)
async def get_instance_health(
    instance_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstanceHealth:
    inst = await db.get(StrategyInstance, instance_id)
    if inst is None or inst.user_id != current.id:
        raise NotFoundError(
            "Strategy instance not found",
            code="STRATEGY_INSTANCE_NOT_FOUND",
        )
    # Count open positions from trades
    from sqlalchemy import func

    open_count = (
        await db.execute(
            select(func.count(Trade.id)).where(
                Trade.strategy_instance_id == instance_id,
                Trade.status == "open",
            )
        )
    ).scalar_one()
    return StrategyInstanceHealth(
        instance_id=inst.id,
        status=inst.status,
        last_heartbeat_at=inst.last_signal_at,
        last_signal_at=inst.last_signal_at,
        open_positions=int(open_count or 0),
        daily_loss_cents=inst.daily_loss_today_cents,
        kill_switch_armed=inst.kill_switch_armed,
    )


@read_router.get(
    "/{instance_id}/signals",
    summary="Recent signals for a strategy instance",
)
async def list_instance_signals(
    instance_id: UUID,
    limit: int = 50,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await db.get(StrategyInstance, instance_id)
    if inst is None or inst.user_id != current.id:
        raise NotFoundError(
            "Strategy instance not found",
            code="STRATEGY_INSTANCE_NOT_FOUND",
        )
    limit = max(1, min(int(limit), 200))
    result = await db.execute(
        select(Signal)
        .where(Signal.strategy_instance_id == instance_id)
        .order_by(desc(Signal.ts))
        .limit(limit)
    )
    return [
        {
            "id": str(s.id),
            "ts": s.ts.isoformat() if s.ts else None,
            "direction": s.direction,
            "price": str(s.price),
            "sl": str(s.sl) if s.sl is not None else None,
            "tp": str(s.tp) if s.tp is not None else None,
            "status": s.status,
        }
        for s in result.scalars().all()
    ]


@read_router.get(
    "/{instance_id}/trades",
    summary="Recent trades for a strategy instance",
)
async def list_instance_trades(
    instance_id: UUID,
    limit: int = 50,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await db.get(StrategyInstance, instance_id)
    if inst is None or inst.user_id != current.id:
        raise NotFoundError(
            "Strategy instance not found",
            code="STRATEGY_INSTANCE_NOT_FOUND",
        )
    limit = max(1, min(int(limit), 200))
    result = await db.execute(
        select(Trade)
        .where(Trade.strategy_instance_id == instance_id)
        .order_by(desc(Trade.created_at))
        .limit(limit)
    )
    return [
        {
            "id": str(t.id),
            "symbol": t.symbol,
            "side": t.side,
            "lot_size": str(t.lot_size),
            "entry_price": str(t.entry_price),
            "exit_price": str(t.exit_price) if t.exit_price is not None else None,
            "status": t.status,
            "net_pnl_cents": t.net_pnl_cents,
            "created_at": t.created_at.isoformat()
            if t.created_at
            else datetime.now(UTC).isoformat(),
        }
        for t in result.scalars().all()
    ]

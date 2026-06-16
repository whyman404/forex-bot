"""Audit-log middleware/dependency — record security-relevant events.

Atlas Goro — audit is *append-only*. Never UPDATE/DELETE audit_log rows.
Use this from services for mutation events; integrated as middleware for HTTP
mutations (POST/PUT/PATCH/DELETE) via AuditMutationMiddleware.

Schema: docs/database/schema.sql §6.2 (audit_log)
Columns: actor_user_id | action | target_type | target_id | payload_redacted | ip_addr | user_agent
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.audit_log import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.requests import Request

logger = get_logger(__name__)


_REDACT_KEYS = {
    "password",
    "new_password",
    "totp_code",
    "totp_secret",
    "credentials",
    "api_key",
    "api_secret",
    "refresh_token",
    "access_token",
}


def _redact(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        out[k] = "***" if k in _REDACT_KEYS else v
    return out


async def record_audit(
    db: "AsyncSession",
    *,
    action: str,
    actor_user_id: UUID | None = None,
    target_type: str | None = None,
    target_id: UUID | str | None = None,
    request: "Request | None" = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Insert an audit row. Must run inside the calling transaction.

    Caller commits — we never autocommit here.
    """
    ip: str | None = None
    ua: str | None = None
    request_id: str | None = None
    if request is not None:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        request_id = getattr(request.state, "request_id", None)

    payload_redacted = _redact(payload)
    if request_id:
        payload_redacted["_request_id"] = request_id

    target_uuid: UUID | None = None
    if isinstance(target_id, str):
        try:
            target_uuid = UUID(target_id)
        except ValueError:
            payload_redacted["target_id_str"] = target_id
            target_uuid = None
    elif isinstance(target_id, UUID):
        target_uuid = target_id

    row = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_uuid,
        payload_redacted=payload_redacted,
        ip_addr=ip,
        user_agent=ua,
    )
    db.add(row)
    logger.info(
        "audit",
        action=action,
        target_type=target_type,
        target_id=str(target_uuid) if target_uuid else None,
    )


class AuditMutationMiddleware(BaseHTTPMiddleware):
    """Record an audit row for every successful mutating HTTP request.

    Skips: GET, HEAD, OPTIONS, /healthz, /readyz, /docs, /openapi.json.
    Only records when response 2xx and request.state.user_id was set by auth dep.
    Failures are logged but never block the response.
    """

    _SKIP_METHODS = {"GET", "HEAD", "OPTIONS"}
    _SKIP_PATHS = {"/healthz", "/readyz", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: "Request", call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)

        if request.method in self._SKIP_METHODS:
            return response
        if request.url.path in self._SKIP_PATHS:
            return response
        if not (200 <= response.status_code < 300):
            return response

        user_id_str = getattr(request.state, "user_id", None)
        actor_uuid: UUID | None = None
        if user_id_str:
            try:
                actor_uuid = UUID(user_id_str)
            except ValueError:
                actor_uuid = None

        try:
            action = f"http.{request.method.lower()} {request.url.path}"
            async with SessionLocal() as session:
                await record_audit(
                    session,
                    action=action,
                    actor_user_id=actor_uuid,
                    target_type="http_request",
                    request=request,
                    payload={"status": response.status_code},
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001 — never let audit block traffic
            logger.warning("audit_persist_failed", err=str(exc))

        return response

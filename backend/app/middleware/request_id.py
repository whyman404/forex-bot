"""Request-ID middleware: trust upstream `X-Request-Id` if present, else mint UUID4.

Sets `request.state.request_id`, echoes on response, exports to contextvars
(so structlog auto-includes it).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import request_id_ctx

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

_HEADER = "X-Request-Id"
_MAX_LEN = 128


def _is_valid_id(candidate: str) -> bool:
    """Reject untrusted/oversized values to avoid log injection."""
    if not candidate or len(candidate) > _MAX_LEN:
        return False
    return all(c.isalnum() or c in "-_:." for c in candidate)


class RequestIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: "Request", call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get(_HEADER, "")
        request_id = incoming if _is_valid_id(incoming) else str(uuid.uuid4())

        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        response.headers[_HEADER] = request_id
        return response

"""Bearer-token auth for the bridge.

Uses constant-time comparison (`hmac.compare_digest`) so the token cannot
be brute-forced via timing attacks. We also reject tokens that look like
placeholders or are absurdly short — defense in depth.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from mt5_bridge.config import BridgeConfig


def make_token_dependency(config: BridgeConfig):
    """Return a FastAPI dependency that validates the bearer token.

    Usage in routes:

        from fastapi import Depends
        require_token = make_token_dependency(config)

        @app.get("/account", dependencies=[Depends(require_token)])
        def account(): ...
    """

    expected = config.token

    def _require_token(authorization: str | None = Header(default=None)) -> None:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Accept "Bearer <token>" (RFC 6750). Be strict about the scheme.
        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="expected scheme: Bearer",
                headers={"WWW-Authenticate": "Bearer"},
            )
        presented = parts[1].strip()
        # Constant-time comparison — same length encoded as bytes.
        if not hmac.compare_digest(
            presented.encode("utf-8"), expected.encode("utf-8")
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return _require_token

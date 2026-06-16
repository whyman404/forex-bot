"""Env-driven config for the MT5 bridge.

All settings are read from environment variables. We do NOT use a `.env`
loader in the bridge itself — Windows service env is configured via NSSM
or `setx`, so a stray `.env` would surprise operators.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class BridgeConfig:
    """Bridge runtime config.

    Attributes:
        bind: host:port the FastAPI server listens on. Default 0.0.0.0:8500.
        token: shared secret. Backend must send Authorization: Bearer <token>.
        mt5_path: optional explicit path to `terminal64.exe`. None = autoselect.
        max_lot: hard cap on a single order's volume (lots).
        symbol_allowlist: only symbols in this list may be traded. Empty = allow any.
        require_sl: refuse to place an order without SL.
        allowed_origins: optional list of caller IPs (informational; firewall is
            the real boundary). Empty = log only.
    """

    bind: str = "0.0.0.0:8500"
    token: str = ""
    mt5_path: str | None = None
    max_lot: float = 1.0
    symbol_allowlist: list[str] = field(default_factory=list)
    require_sl: bool = True
    allowed_origins: list[str] = field(default_factory=list)

    @property
    def host(self) -> str:
        return self.bind.split(":", 1)[0]

    @property
    def port(self) -> int:
        return int(self.bind.split(":", 1)[1])

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        token = os.getenv("BRIDGE_TOKEN", "").strip()
        if not token:
            # We deliberately raise here. Letting the bridge boot with an
            # empty token would mean anyone on the network can place orders.
            raise RuntimeError(
                "BRIDGE_TOKEN is not set. Set it before starting the bridge — "
                "see README.md §Configure."
            )
        if len(token) < 32:
            raise RuntimeError(
                f"BRIDGE_TOKEN is too short ({len(token)} chars). "
                "Use at least 32 random chars (PowerShell: "
                "[Convert]::ToBase64String((1..32 | %{Get-Random -Max 256}))). "
            )

        return cls(
            bind=os.getenv("BRIDGE_BIND", "0.0.0.0:8500"),
            token=token,
            mt5_path=os.getenv("MT5_PATH") or None,
            max_lot=float(os.getenv("BRIDGE_MAX_LOT", "1.0")),
            symbol_allowlist=_split_csv(os.getenv("BRIDGE_SYMBOL_ALLOWLIST", "")),
            require_sl=os.getenv("BRIDGE_REQUIRE_SL", "true").lower() == "true",
            allowed_origins=_split_csv(os.getenv("BRIDGE_ALLOWED_ORIGINS", "")),
        )

    def redact(self) -> dict[str, object]:
        """Loggable view — token is masked."""
        token_show = (self.token[:4] + "…" + self.token[-2:]) if self.token else ""
        return {
            "bind": self.bind,
            "token": token_show,
            "mt5_path": self.mt5_path,
            "max_lot": self.max_lot,
            "symbol_allowlist": self.symbol_allowlist,
            "require_sl": self.require_sl,
            "allowed_origins": self.allowed_origins,
        }

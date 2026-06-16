"""Symbol → (TV symbol, exchange) mapping.

TradingView screener needs both a symbol AND an exchange (because XAUUSD
exists on OANDA, FXOPEN, EIGHTCAP — and the recommendation differs).

We hardcode a curated mapping for the assets the bot currently supports.
Unknown symbols fall back to (symbol, "FX_IDC") which is TV's "neutral"
forex feed — works for most majors but may return less accurate signals.

For crypto we prefer BINANCE (most liquid USDT pairs).

Add a new symbol here AND update `configs/strategies.yaml` if you want it
to appear in the UI's "supported pairs" dropdown.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TVSymbol:
    """One TradingView-tradable instrument."""

    symbol: str          # TV ticker, e.g. "XAUUSD"
    exchange: str        # TV exchange code, e.g. "OANDA"
    asset_class: str     # "gold" | "forex" | "crypto"
    display_name: str    # human label for UI


# Curated mapping — internal_symbol → TVSymbol.
# Keep this list small + intentional. Don't auto-generate.
SUPPORTED_SYMBOLS: dict[str, TVSymbol] = {
    # Gold (XAUUSD) — OANDA is the most reliable feed on TV for retail bots.
    "XAUUSD": TVSymbol("XAUUSD", "OANDA", "gold", "Gold / USD (OANDA)"),

    # Major forex pairs — OANDA used as canonical retail FX feed.
    "EURUSD": TVSymbol("EURUSD", "OANDA", "forex", "EUR / USD"),
    "GBPUSD": TVSymbol("GBPUSD", "OANDA", "forex", "GBP / USD"),
    "USDJPY": TVSymbol("USDJPY", "OANDA", "forex", "USD / JPY"),
    "USDCHF": TVSymbol("USDCHF", "OANDA", "forex", "USD / CHF"),
    "AUDUSD": TVSymbol("AUDUSD", "OANDA", "forex", "AUD / USD"),
    "NZDUSD": TVSymbol("NZDUSD", "OANDA", "forex", "NZD / USD"),
    "USDCAD": TVSymbol("USDCAD", "OANDA", "forex", "USD / CAD"),

    # Cross pairs
    "EURJPY": TVSymbol("EURJPY", "OANDA", "forex", "EUR / JPY"),
    "GBPJPY": TVSymbol("GBPJPY", "OANDA", "forex", "GBP / JPY"),
    "EURGBP": TVSymbol("EURGBP", "OANDA", "forex", "EUR / GBP"),

    # Crypto — BINANCE is the deepest USDT feed.
    "BTCUSDT": TVSymbol("BTCUSDT", "BINANCE", "crypto", "Bitcoin / USDT"),
    "ETHUSDT": TVSymbol("ETHUSDT", "BINANCE", "crypto", "Ethereum / USDT"),
    "SOLUSDT": TVSymbol("SOLUSDT", "BINANCE", "crypto", "Solana / USDT"),
    "BNBUSDT": TVSymbol("BNBUSDT", "BINANCE", "crypto", "BNB / USDT"),

    # Indices (informational only — we don't trade these yet)
    "SPX500": TVSymbol("SPX500USD", "OANDA", "index", "S&P 500"),
    "NAS100": TVSymbol("NAS100USD", "OANDA", "index", "Nasdaq 100"),
}


def resolve_symbol(symbol: str, exchange: str | None = None) -> TVSymbol:
    """Resolve our internal symbol to a TV (symbol, exchange) pair.

    If `exchange` is provided it overrides the default mapping (useful when
    a user wants to use FXOPEN's XAUUSD feed instead of OANDA's). The
    `asset_class` from SUPPORTED_SYMBOLS is preserved.

    Falls back to (symbol, "FX_IDC", "forex") for unknown symbols — better
    to attempt than to fail hard. Caller should log a warning.
    """
    base = SUPPORTED_SYMBOLS.get(symbol.upper())
    if base is None:
        # Unknown — best-effort fallback.
        return TVSymbol(
            symbol=symbol.upper(),
            exchange=exchange or "FX_IDC",
            asset_class="forex",
            display_name=symbol.upper(),
        )
    if exchange and exchange != base.exchange:
        return TVSymbol(
            symbol=base.symbol,
            exchange=exchange.upper(),
            asset_class=base.asset_class,
            display_name=f"{base.display_name} ({exchange.upper()})",
        )
    return base


def list_supported() -> list[dict[str, str]]:
    """Return a JSON-friendly list of supported symbols for the API."""
    out: list[dict[str, str]] = []
    for internal, tv in SUPPORTED_SYMBOLS.items():
        out.append(
            {
                "internal_symbol": internal,
                "tv_symbol": tv.symbol,
                "tv_exchange": tv.exchange,
                "asset_class": tv.asset_class,
                "display_name": tv.display_name,
            }
        )
    return out

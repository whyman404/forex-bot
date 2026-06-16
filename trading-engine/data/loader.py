"""Data loaders.

- `load_mt5_csv(path)` — MT5 standard CSV (date,open,high,low,close,volume).
- `load_parquet(path)` — Parquet (faster for re-use after first load).
- `download_binance_klines(...)` — pulls OHLCV from Binance via ccxt.
- `load_sample(symbol, timeframe)` — read pre-generated dev CSV.

All loaders return a `pd.DataFrame` with:
    - tz-aware UTC DatetimeIndex
    - columns: ['open', 'high', 'low', 'close', 'volume']  (lowercase)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

_EXPECTED_COLS = ["open", "high", "low", "close", "volume"]
_SAMPLES_DIR = Path(__file__).parent / "samples"


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure schema: lowercase cols, UTC DatetimeIndex, sorted."""
    df = df.rename(columns={c: c.lower() for c in df.columns})
    missing = [c for c in _EXPECTED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}; got {df.columns.tolist()}")
    if not isinstance(df.index, pd.DatetimeIndex):
        # try common column names
        for c in ("time", "datetime", "date", "timestamp"):
            if c in df.columns:
                df = df.set_index(pd.to_datetime(df[c], utc=True)).drop(columns=[c])
                break
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    return df[_EXPECTED_COLS]


def load_mt5_csv(path: str | Path) -> pd.DataFrame:
    """Load a CSV exported from MT5 (Tools → History Center → Export).

    Accepts the standard MT5 schema:
        Date, Time, Open, High, Low, Close, Volume
    or merged-datetime variants. Falls back gracefully.
    """
    path = Path(path)
    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() for c in raw.columns]
    if "date" in raw.columns and "time" in raw.columns:
        raw["datetime"] = pd.to_datetime(
            raw["date"].astype(str) + " " + raw["time"].astype(str), utc=True
        )
        raw = raw.drop(columns=["date", "time"])
    if "volume" not in raw.columns and "tickvol" in raw.columns:
        raw = raw.rename(columns={"tickvol": "volume"})
    return _normalize(raw)


def load_parquet(path: str | Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    return _normalize(df)


def download_binance_klines(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start: str | dt.datetime = "2023-01-01",
    end: str | dt.datetime | None = None,
    exchange_name: str = "binance",
) -> pd.DataFrame:
    """Download OHLCV from a ccxt exchange and return a normalized DataFrame.

    NOTE: ccxt is an optional runtime dep — caller must `uv sync` first.
    """
    try:
        import ccxt  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "ccxt not installed. Run `uv sync` first."
        ) from e

    exchange = getattr(ccxt, exchange_name)({"enableRateLimit": True})
    start_ts = int(pd.to_datetime(start, utc=True).timestamp() * 1000)
    end_ts = (
        int(pd.to_datetime(end, utc=True).timestamp() * 1000)
        if end
        else int(dt.datetime.utcnow().timestamp() * 1000)
    )

    rows: list[list[float]] = []
    since = start_ts
    limit = 1000
    while since < end_ts:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        if not batch:
            break
        rows.extend(batch)
        since = int(batch[-1][0]) + 1
        if len(batch) < limit:
            break

    if not rows:
        return pd.DataFrame(columns=_EXPECTED_COLS)
    df = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
    df = df.set_index("datetime")
    return _normalize(df)


# ---------------------------------------------------------------------------
# Sample loader — for offline dev / CI / tests
# ---------------------------------------------------------------------------
_SAMPLE_FILES: dict[tuple[str, str], str] = {
    ("XAUUSD", "M5"): "XAUUSD_M5_sample.csv",
    ("XAUUSD", "H1"): "XAUUSD_H1_sample.csv",
    ("BTCUSDT", "H1"): "BTCUSDT_H1_sample.csv",
    ("BTCUSDT", "H4"): "BTCUSDT_H4_sample.csv",
}


def load_sample(symbol: str, timeframe: str) -> pd.DataFrame:
    """Load a pre-generated sample OHLCV CSV.

    The samples live in `data/samples/` and are reproduced by
    `data/samples/generate.py`. They are small (<100KB) and seeded so the
    dev container + CI both get deterministic data without network access.

    Args:
        symbol: e.g. "XAUUSD", "BTCUSDT".
        timeframe: e.g. "M5", "M15", "H1", "H4".

    Raises:
        FileNotFoundError: if no sample exists for the given pair. In that
            case, fall back to the nearest available timeframe for the symbol.
    """
    key = (symbol.upper(), timeframe.upper())
    fname = _SAMPLE_FILES.get(key)
    if fname is None:
        # Fallback: any sample for this symbol.
        candidates = [
            (s, t, f) for (s, t), f in _SAMPLE_FILES.items() if s == symbol.upper()
        ]
        if not candidates:
            raise FileNotFoundError(
                f"No sample data for {symbol} (any timeframe). "
                f"Have: {list(_SAMPLE_FILES.keys())}"
            )
        _, _, fname = candidates[0]
    path = _SAMPLES_DIR / fname
    if not path.exists():
        raise FileNotFoundError(
            f"Sample CSV missing: {path}. Run `python data/samples/generate.py` "
            f"to regenerate."
        )
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime")
    return _normalize(df)

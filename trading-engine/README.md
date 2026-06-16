# Trading Engine

Python trading engine for the Forex/Crypto SaaS bot. Implements 6 strategies, a
backtest runner (vectorbt), risk management, broker adapters (MT5 + Binance
paper), **a FastAPI service** for backend integration, and an **RQ worker** for
async backtests.

**Owner:** Kairos Toki — Quant Engineer.

---

## What's here

```
trading-engine/
├── pyproject.toml
├── README.md
├── Dockerfile              # multi-stage; modes: server | worker
├── server.py               # FastAPI app — /run-backtest, /test-mt5, /healthz
├── strategies/             # 6 strategy implementations + base class
│   ├── base.py
│   ├── london_breakout.py
│   ├── ny_killzone.py
│   ├── ema_adx_trend.py
│   ├── ema_rsi_swing.py
│   ├── donchian_breakout.py
│   └── grid_bot.py
├── backtest/
│   ├── runner.py           # vectorbt-driven runner → metrics
│   └── walk_forward.py     # rolling in-sample / out-of-sample
├── risk/
│   ├── manager.py          # circuit breakers, daily loss, max DD
│   └── position_sizing.py  # fixed-fractional, ATR, Kelly (capped)
├── broker/
│   ├── base.py             # abstract Broker
│   ├── mt5_adapter.py      # MetaTrader5 (Windows-only at runtime)
│   └── paper_adapter.py    # simulated fills, slippage model
├── workers/
│   ├── backtest_worker.py  # run_backtest_job() — in-proc + RQ
│   └── queue.py            # Redis + RQ helpers (enqueue, status)
├── data/
│   ├── loader.py           # CSV / Parquet + ccxt + load_sample()
│   ├── symbols.py          # contract sizes, pip values, baseline spreads
│   └── samples/
│       ├── generate.py     # seeded synthetic OHLCV generator
│       └── *.csv           # pre-generated sample data (committed)
├── configs/
│   └── strategies.yaml     # default params (overridable per user)
└── tests/
    ├── test_strategies_smoke.py
    └── test_backtest_api.py
```

---

## Install

We use **uv** as the package manager (faster than pip, deterministic).

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# In trading-engine/
uv sync

# Optional: install MT5 (Windows VPS only)
uv sync --extra mt5

# Optional: install TA-Lib (needs system C lib first)
#   macOS:  brew install ta-lib
#   Ubuntu: sudo apt-get install ta-lib
uv sync --extra talib

# Dev tooling (pytest, ruff)
uv sync --extra dev
```

> If `MetaTrader5` fails to install on Mac/Linux, that is expected — the marker
> `platform_system == 'Windows'` keeps it optional. Imports are guarded.

---

## Quick start

### Run smoke tests

```bash
uv run pytest tests/ -v
```

This confirms every strategy imports + produces a `signals()` DataFrame, and
that the FastAPI surface (run-backtest, equity-curve, healthz) works against
the seeded sample CSVs in `data/samples/`.

### Run the FastAPI server (dev)

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8500 --reload
```

Then poke it:

```bash
curl http://localhost:8500/healthz

curl -X POST http://localhost:8500/run-backtest \
  -H 'content-type: application/json' \
  -d '{
        "strategy_code": "london_breakout",
        "asset": "XAUUSD",
        "timeframe": "M5",
        "start_date": "2025-06-02",
        "end_date": "2025-06-06",
        "params": {}
      }'

# returns { "backtest_id": "...", "status": "accepted", ... }
curl http://localhost:8500/backtest/<id>/equity-curve
```

### Run an RQ worker (Phase 2 path)

```bash
# Requires Redis running at $REDIS_URL (default redis://localhost:6379/0)
uv run rq worker backtest
```

The backend (Atlas) can then call `workers.queue.enqueue_backtest(...)` and the
worker will process jobs out of band.

### Run via Docker

```bash
docker build -t forex-bot/trading-engine .

# Default = FastAPI server.
docker run --rm -p 8500:8500 forex-bot/trading-engine

# Worker mode.
docker run --rm --env REDIS_URL=redis://redis:6379/0 forex-bot/trading-engine worker
```

### Regenerate sample data

```bash
uv run python data/samples/generate.py
```

The CSVs are seeded — every run reproduces the same bytes.

### Backtest a strategy

```python
from data.loader import load_mt5_csv
from strategies.london_breakout import LondonBreakoutStrategy
from backtest.runner import run_backtest

df = load_mt5_csv("data/XAUUSD_M5.csv")
strat = LondonBreakoutStrategy()
report = run_backtest(strat, df, cost_model="exness_gold")
print(report["summary"])
```

### Walk-forward analysis

```python
from backtest.walk_forward import walk_forward
wf = walk_forward(strat, df, n_splits=5, train_ratio=0.7)
print(wf["per_window"])
print(wf["parameter_stability"])
```

### Paper trading

```python
from broker.paper_adapter import PaperBroker
broker = PaperBroker(initial_balance=10_000, slippage_pips=1.0)
# ... feed live ticks, broker.place_order(...)
```

### MT5 live (Windows VPS only)

```python
from broker.mt5_adapter import MT5Broker  # import-safe even on Mac
broker = MT5Broker(account=12345, password="...", server="Exness-Real")
broker.connect()
```

---

## Realistic cost assumptions

| Asset    | Cost model                                                                |
| -------- | ------------------------------------------------------------------------- |
| XAU/USD  | Spread 20 pts (≈ $0.20 per 0.01 lot round-trip), slippage 0.5 pip, no commission |
| BTC/USDT | Taker fee 0.05% (Binance VIP-0), slippage 0.02% on aggressive entries     |

Backtest defaults already include these. Disable them only if you know what
you're doing.

---

## What's NOT here (yet)

- Live execution loop (event-driven OMS) — comes Phase 2.
- ML / regime detection layer — Phase 4.
- Multi-account routing — Phase 2.
- S3 artifact uploader (equity curves currently stored at
  `/var/data/equity-curves/{id}.json`) — Phase 2.

See `docs/strategies/` at the project root for strategy specs and the
"reality check" doc on win rate vs expectancy. See
`docs/strategies/backtest-api.md` for the FastAPI contract that Atlas uses.
